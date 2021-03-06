import asyncio
import re
import xml.etree.ElementTree as ET
import string
import pickle
import os
import threading
import queue
from itertools import count
from struct import unpack
from enum import IntEnum
from typing import List
from ipaddress import IPv4Address
from datetime import datetime
from collections import defaultdict

from .. import logger, Session, Base, Packages, ROOT_DIR
from .x55_protocol import (
    Request,
    GetFirmwareVersion,
    GetInstrumentName,
    IsReady,
    GetDutChannelCount,
    EnablePeakDataStreaming,
    DisablePeakDataStreaming,
    GetPeakDataStreamingStatus,
    GetPeakDataStreamingDivider,
    SetPeakDataStreamingDivider,
    GetPeakDataStreamingAvailableBuffer,
    GetLaserScanSpeed,
    SetLaserScanSpeed,
    GetAvailableLaserScanSpeeds,
    SetInstrumentUtcDateTime,
    GetInstrumentUtcDateTime,
    GetNtpEnabled,
    SetNtpEnabled,
    GetNtpServer,
    SetNtpServer,
    Response,
    FirmwareVersion,
    InstrumentName,
    Ready,
    DutChannelCount,
    Peaks,
    PeakDataStreamingStatus,
    PeakDataStreamingDivider,
    PeakDataStreamingAvailableBuffer,
    LaserScanSpeed,
    AvailableLaserScanSpeeds,
    InstrumentUtcDateTime,
    NtpEnabled,
    NtpServer,
)

HOST = "10.0.0.55"
COMMAND_PORT = 51971
PEAK_STREAMING_PORT = 51972
HEADER_LENGTH = 8


class SetupOptions(IntEnum):
    BASEMENT_AND_FRAME = 0
    STRONG_FLOOR = 1
    BASEMENT = 2
    FRAME = 3

    def __str__(self):
        return self._name_.replace("_", " ")


class Configuration:
    def __init__(self):
        self.mapping = None  # For every table, for every channel, map an index to an ID
        self.setup = None  # Store the current sensor setup
        self.load(SetupOptions.BASEMENT_AND_FRAME)

    @property
    def packages(self):
        """
        Return the packages associated with the current sensor setup.
        """
        if self.setup == SetupOptions.BASEMENT_AND_FRAME:
            return (
                Packages.basement,
                Packages.steel_frame,
            )
        if self.setup == SetupOptions.STRONG_FLOOR:
            return (Packages.strong_floor,)
        if self.setup == SetupOptions.BASEMENT:
            return (Packages.basement,)
        if self.setup == SetupOptions.FRAME:
            return (Packages.steel_frame,)

    def map(self, peaks: List[List[float]], table: Base):
        """
        Map the optical instrument output peaks array of arrays to UID: value pairs for the given database table.
        To turn off the recording of individual sensors change its measurement_type to "off".
        If a sensor can no longer be read at all by the optical instrument, remove its row from the metadata table entirely.
        """
        mapped_peaks = {}
        for uid, metadata in self.mapping[table].items():
            channel = metadata.channel
            index = metadata.index
            recording = metadata.recording
            minimum_wavelength = metadata.minimum_wavelength
            maximum_wavelength = metadata.maximum_wavelength

            # Skip disabled sensors
            if not recording:
                continue

            # Search peaks[channel] array for a matching sensor
            # Readings may accidentally be dropped, but extra readings cannot be added, therefore
            # the sensor's actual index can only be equal to or lower than the expected index
            for measurement in peaks[channel][index::-1]:  # Start at the expected index
                if minimum_wavelength < measurement < maximum_wavelength:
                    mapped_peaks[uid] = measurement
                    break
                # Otherwise the sensor has been dropped or is out-of-band, so ignore

        return mapped_peaks

    def load(self, setup: SetupOptions):
        """
        Load a new configuration from database metadata tables.
        """
        self.setup = setup
        self.mapping = {}  # {Basement: {"A1": row, ...}, ... }

        # Load in metadata from tables to mapping
        session = Session()
        for package in self.packages:
            self.mapping[package.values_table] = {
                row.uid: row for row in session.query(package.metadata_table).all()
            }
        session.close()

        logger.info("Loaded configuration from database")

        return self.setup

    def parse(self, config_file):
        """
        Parse and save a configuration to the database metadata tables.
        Any sensor UIDs or names referenced in the file that exist will be updated,
        but additional UIDs or names in the file will be ignored. It is therefore
        safe to update just Basement metadata table from a combined config file, whilst
        it is also safe to update both the Basement and Steel Frame metadata tables simultaneously.
        """
        session = Session()

        root = ET.parse(config_file).getroot()

        for package in self.packages:
            # Data associated with a UID
            for sensor in root.iter("SensorConfiguration"):
                uid = re.search("[^_]{1,3}$", sensor.find("Name").text)[0]
                reference_wavelength = sensor.find("Reference").text
                minimum_wavelength = sensor.find("WavelengthMinimum").text
                maximum_wavelength = sensor.find("WavelengthMaximum").text

                channel = string.ascii_uppercase.index(uid[0])
                index = int(uid[1:]) - 1

                data = {
                    "channel": channel,
                    "index": index,
                    "reference_wavelength": reference_wavelength,
                    "minimum_wavelength": minimum_wavelength,
                    "maximum_wavelength": maximum_wavelength,
                }
                if data:
                    session.query(package.metadata_table).filter(
                        package.metadata_table.uid == uid
                    ).update(data)

            # Data associated with a sensor name
            for transducer in root.iter("Transducer"):
                name = transducer.find("ID").text
                coeffs = {}
                for constant in transducer.iter("TransducerConstant"):
                    constant_name = constant.find("Name").text
                    constant_value = float(constant.find("Value").text)

                    if constant_name.startswith("FBG") and constant_name.endswith("0"):
                        uid = re.search("_([^;]*)_", constant_name)[1]
                        session.query(package.metadata_table).filter(
                            package.metadata_table.uid == uid
                        ).update({"initial_wavelength": constant_value})

                    else:
                        # Handle edge cases caused by lack of formulas and differently named coefficients in Enlight
                        if constant_name == "K":  # beta is sometimes called K
                            constant_name = "beta"
                        elif (
                            constant_name == "CTEt"
                        ):  # CTEt is in units 10^-6/C in Enlight
                            constant_value /= 1e6
                        elif constant_name == "St":  # Also record St in tmp sensor row
                            sensor = (
                                session.query(package.metadata_table)
                                .filter(package.metadata_table.name == name)
                                .first()
                            )
                            if sensor and sensor.type == "str":
                                tmp_uid = sensor.corresponding_sensor
                                session.query(package.metadata_table).filter(
                                    package.metadata_table.uid == tmp_uid
                                ).update({"coeffs": {"St": constant_value}})

                        coeffs[constant_name] = constant_value

                if coeffs:
                    session.query(package.metadata_table).filter(
                        package.metadata_table.name == name
                    ).update({"coeffs": coeffs})

        session.commit()
        session.close()

        logger.info("Uploaded new configuration file to database")

        self.load(self.setup)  # Load the newly parsed config file


class Connection:
    def __init__(self, name: str, host: str, port: int):
        self.name = name
        self.host = host
        self.port = port
        self.reader = None
        self.writer = None
        self.reading = asyncio.Condition()

    async def connect(self):
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        logger.info("%s connected to %s:%d", self.name, self.host, self.port)

    async def disconnect(self):
        if self.writer is not None:
            self.writer.close()
            await self.writer.wait_closed()
            logger.info("%s disconnected from %s:%d", self.name, self.host, self.port)

    async def read(self) -> bytes:
        async with self.reading:
            header = await self.reader.readexactly(HEADER_LENGTH)
            status = not unpack("<?", header[0:1])[0]  # True if successful
            message_size = unpack("<H", header[2:4])[0]
            content_size = unpack("<I", header[4:8])[0]
            response = await self.reader.readexactly(message_size + content_size)
            message = response[:message_size]
            content = response[message_size : message_size + content_size]

            return status, message, content

    async def execute(self, request: Request) -> bytes:
        self.writer.write(request.serialize())
        return await self.read()


class x55Client:
    """
    Client to interact with an si255 fibre optic analyser box. Reflects the TCP protocol as far as possible.
    See the Micron Optics User Guide, Revision 2017.09.30 section 6 for details.
    """

    _count = count(1)

    def __init__(self):
        self.name = f"x55 Client {next(self._count)}"

        # Connection information
        self.host = HOST
        self.command = None
        self.peaks = None
        self.connected = False

        # Options
        self.divider_options = [1, 10, 100]

        # Status information
        self.instrument_name = None
        self.firmware_version = None
        self.is_ready = None
        self.dut_channel_count = None
        self.available_laser_scan_speeds = [None]
        self.peak_data_streaming_status = None
        self.laser_scan_speed = None
        self.peak_data_streaming_divider = None
        self.peak_data_streaming_available_buffer = None
        self.laser_scan_speed = None
        self.instrument_time = None
        self.ntp_enabled = None
        self.ntp_server = None

        # Recording and streaming toggles
        self.recording = False
        self.streaming = False

        # Configuration setting
        self.configuration = Configuration()

        # Database writing queue
        self.queues = defaultdict(queue.SimpleQueue)

    @property
    def effective_sampling_rate(self):
        if (self.laser_scan_speed and self.peak_data_streaming_divider) is None:
            return None
        return self.laser_scan_speed // self.peak_data_streaming_divider

    async def connect(self):
        self.command = Connection(self.name, self.host, COMMAND_PORT)
        self.peaks = Connection(self.name, self.host, PEAK_STREAMING_PORT)
        await self.command.connect()
        self.connected = True

    async def disconnect(self):
        await self.command.disconnect()
        await self.peaks.disconnect()
        self.connected = False

    async def update_status(self):
        self.instrument_name = InstrumentName(
            await self.command.execute(GetInstrumentName())
        ).content

        self.firmware_version = FirmwareVersion(
            await self.command.execute(GetFirmwareVersion())
        ).content

        self.is_ready = Ready(await self.command.execute(IsReady())).content

        self.dut_channel_count = DutChannelCount(
            await self.command.execute(GetDutChannelCount())
        ).content

        self.available_laser_scan_speeds = AvailableLaserScanSpeeds(
            await self.command.execute(GetAvailableLaserScanSpeeds())
        ).content

        self.peak_data_streaming_status = PeakDataStreamingStatus(
            await self.command.execute(GetPeakDataStreamingStatus())
        ).content

        self.laser_scan_speed = LaserScanSpeed(
            await self.command.execute(GetLaserScanSpeed())
        ).content

        self.peak_data_streaming_divider = PeakDataStreamingDivider(
            await self.command.execute(GetPeakDataStreamingDivider())
        ).content

        self.peak_data_streaming_available_buffer = PeakDataStreamingAvailableBuffer(
            await self.command.execute(GetPeakDataStreamingAvailableBuffer())
        ).content

        self.instrument_time = InstrumentUtcDateTime(
            await self.command.execute(GetInstrumentUtcDateTime())
        ).content

        self.ntp_enabled = NtpEnabled(
            await self.command.execute(GetNtpEnabled())
        ).content

        self.ntp_server = NtpServer(await self.command.execute(GetNtpServer())).content

    async def update_laser_scan_speed(self, laser_scan_speed: int) -> bool:
        await self.command.execute(SetLaserScanSpeed(speed=laser_scan_speed))

        self.laser_scan_speed = LaserScanSpeed(
            await self.command.execute(GetLaserScanSpeed())
        ).content

        logger.info("Laser scan speed set to: %d", self.laser_scan_speed)
        return self.laser_scan_speed

    async def update_peak_data_streaming_divider(self, divider: int):
        await self.command.execute(SetPeakDataStreamingDivider(divider=divider))

        self.peak_data_streaming_divider = PeakDataStreamingDivider(
            await self.command.execute(GetPeakDataStreamingDivider())
        ).content

        logger.info(
            "Peak data streaming divider set to: %d", self.peak_data_streaming_divider
        )
        return self.peak_data_streaming_divider

    async def update_setup(self, setup: SetupOptions):
        return self.configuration.load(setup)

    async def update_ntp_server(self, address: IPv4Address):
        await self.command.execute(SetNtpEnabled(enabled=False))
        await self.command.execute(SetInstrumentUtcDateTime(dt=datetime.utcnow()))
        await self.command.execute(SetNtpServer(address=address))
        await self.command.execute(SetNtpEnabled(enabled=True))

        self.ntp_server = NtpServer(await self.command.execute(GetNtpServer())).content
        self.ntp_enabled = NtpEnabled(
            await self.command.execute(GetNtpEnabled())
        ).content

        logger.info("Updated NTP server address to: %s", self.ntp_server)
        return self.ntp_server

    async def stream(self):
        await self.peaks.connect()
        self.streaming = Response(
            await self.command.execute(EnablePeakDataStreaming())
        ).status
        logger.info("%s started streaming", self.name)

        while self.streaming:
            yield Peaks(await self.peaks.read())

        # Disconnect and clear out the remaining data from the buffer
        await self.command.execute(DisablePeakDataStreaming())

        buffer = bytes()
        while True:
            try:
                data = await asyncio.wait_for(self.peaks.reader.read(), timeout=0.1)
            except asyncio.TimeoutError:
                break
            buffer += data

        await self.peaks.disconnect()

        # Log the size of the unprocessed buffer
        logger.info(
            "%s stopped streaming with %d unproccessed bytes in the TCP buffer",
            self.name,
            len(buffer),
        )

    def set_live_status(self, live: bool):
        status = {
            "live": live,
            "packages": self.configuration.packages,
            "sampling_rate": self.effective_sampling_rate,
        }
        with open(os.path.join(ROOT_DIR, "var/status.pickle"), "wb") as f:
            pickle.dump(status, f)

    def database_writer(self, q):
        session = Session()

        rows = []

        while self.recording or not q.empty():
            try:
                rows.append(q.get(block=True, timeout=0.1))
            except queue.Empty:
                continue

            # Bulk INSERT and COMMIT every 0.1s
            if len(rows) > 0.1 * self.effective_sampling_rate:
                session.bulk_save_objects(rows)
                session.commit()
                rows = []

        session.bulk_save_objects(rows)
        session.commit()
        session.close()

    async def record(self):
        self.set_live_status(True)

        self.recording = True
        writer_threads = [
            threading.Thread(target=self.database_writer, args=(self.queues[table],))
            for table in self.configuration.mapping
        ]
        for writer_thread in writer_threads:
            writer_thread.start()

        logger.info("Started writer threads")

        async for response in self.stream():
            for table in self.configuration.mapping:
                peaks = self.configuration.map(response.content, table)

                # Send row to the database writer thread
                self.queues[table].put(table(timestamp=response.timestamp, **peaks))

        # Toggle recording off and then wait for thread to finish
        self.recording = False
        logger.info("Waiting for writer threads to join")
        for writer_thread in writer_threads:
            writer_thread.join()
        logger.info("Writer threads joined")

        self.set_live_status(False)
