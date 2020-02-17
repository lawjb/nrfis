from sqlalchemy import Column, String, Float, Integer, Boolean

from . import Base


class BasementMetadata(Base):
    __tablename__ = "basement_fbg_metadata"

    uid = Column(String, primary_key=True)
    channel = Column(Integer)
    index = Column(Integer)
    name = Column(String, unique=True)
    type = Column(String)
    recording = Column(Boolean)
    corresponding_sensor = Column(String)
    reference_wavelength = Column(Float)
    minimum_wavelength = Column(Float)
    maximum_wavelength = Column(Float)
    initial_wavelength = Column(Float)
    Fg = Column(Float)
    eta = Column(Float)
    beta = Column(Float)


class StrongFloorMetadata(Base):
    __tablename__ = "strong_floor_fbg_metadata"

    uid = Column(String, primary_key=True)
    channel = Column(Integer)
    index = Column(Integer)
    name = Column(String, unique=True)
    type = Column(String)
    recording = Column(Boolean)
    corresponding_sensor = Column(String)
    reference_wavelength = Column(Float)
    minimum_wavelength = Column(Float)
    maximum_wavelength = Column(Float)
    initial_wavelength = Column(Float)
    Fg = Column(Float)
    eta = Column(Float)
    beta = Column(Float)


class SteelFrameMetadata(Base):
    __tablename__ = "steel_frame_fbg_metadata"

    uid = Column(String, primary_key=True)
    channel = Column(Integer)
    index = Column(Integer)
    name = Column(String, unique=True)
    type = Column(String)
    recording = Column(Boolean)
    corresponding_sensor = Column(String)
    reference_wavelength = Column(Float)
    minimum_wavelength = Column(Float)
    maximum_wavelength = Column(Float)
    initial_wavelength = Column(Float)
    Fg = Column(Float)
    CTEt = Column(Float)
    St = Column(Float)

