import React, { useState, useContext, useEffect } from "react";
import { View } from "react-native";

import Menu from "./Menu";
import Model from "./Model";
import Chart from "./Chart";
import {
  fetchData,
  fetchTemperatureData,
  theme,
  chartColours,
  modelColourScale,
  LiveStatusContext,
} from "../utils";

export default function Screen(props) {
  const [data, setData] = useState([]);
  const [mode, setMode] = useState(0); // 0 for Model, 1 for Chart
  const [live, setLive] = useState(false);
  const [liveMode, setLiveMode] = useState(1); // 0 for Live, 1 for Historical
  const [dataRange, setDataRange] = useState([]);
  const [dataType, setDataType] = useState("str");
  const [isLoading, setIsLoading] = useState(false);
  const [chartOptions, setChartOptions] = useState({
    sensors: [], // [{ name: sensorName, isSelected: true}, ... }]
    showTemperature: false,
    temperatureData: [], // [{temperature: x, timestamp: x}, ...]
  });
  const [modelOptions, setModelOptions] = useState({
    showContext: true,
    colourMode: 0, // 0 = adaptive
    scale: [0, 0],
  });

  const { packages: livePackages } = useContext(LiveStatusContext);

  useEffect(() => {
    const live = livePackages.includes(props.packageServerName);
    setLive(live);
    if (!live) {
      // Set to historical mode when package is not live
      setLiveMode(1);
    }
  }, [livePackages]);

  async function refresh(dataType, averagingWindow, startTime, endTime) {
    setIsLoading(true);
    try {
      // Fetch sensor data
      const data = await fetchData(
        props.packageURL,
        dataType,
        averagingWindow,
        startTime.toISOString(),
        endTime.toISOString()
      );
      setData(data);
      setDataType(dataType);
      const allReadings = data.reduce(
        (acc, { timestamp, ...readings }) =>
          acc.concat(Object.values(readings)),
        []
      );
      const dataRange = [Math.min(...allReadings), Math.max(...allReadings)];
      setDataRange(dataRange);

      // Switch to chart mode if using raw data type
      if (dataType === "raw") {
        setMode(1); // Chart mode
      }

      // Set chart options
      const { timestamp, ...readings } = data[0]; // Extract sensor readings for the first sample
      const sensorNames = Object.keys(readings); // Extract the sensor names
      setChartOptions({
        ...chartOptions,
        sensors: sensorNames.map((sensorName, index) => ({
          name: sensorName,
          isSelected: index < 3, // By default display only the first three sensors on the chart
          colour: chartColours[index % chartColours.length],
        })),
        temperatureData: await fetchTemperatureData(startTime, endTime),
      });

      // Set model options
      setModelOptions({
        ...modelOptions,
        scale: modelOptions.colourMode ? modelColourScale[dataType] : dataRange,
      });
    } catch (error) {
      console.error(error);
    }
    setIsLoading(false);
  }

  function renderVisualisation() {
    if (mode == 0) {
      // Model
      return (
        <Model data={data} modelOptions={modelOptions}>
          {({ rotation, zoom, sensorColours }) =>
            props.children({
              rotation,
              zoom,
              sensorColours,
              showContext: modelOptions.showContext,
            })
          }
        </Model>
      );
    } else {
      // Chart
      return <Chart data={data} chartOptions={chartOptions} />;
    }
  }

  return (
    <View style={{ flex: 1, flexDirection: "row" }}>
      <View style={{ flex: 5 }}>{renderVisualisation()}</View>
      <Menu
        style={{
          flex: 2,
          borderLeftWidth: 2,
          borderColor: theme.colors.border,
          padding: 10,
          backgroundColor: theme.colors.background,
        }}
        mode={mode}
        setMode={setMode}
        live={live}
        liveMode={liveMode}
        setLiveMode={setLiveMode}
        dataType={dataType}
        dataRange={dataRange}
        isLoading={isLoading}
        refresh={refresh}
        chartOptions={chartOptions}
        setChartOptions={setChartOptions}
        modelOptions={modelOptions}
        setModelOptions={setModelOptions}
      />
    </View>
  );
}
