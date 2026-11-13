import { useEffect, useRef } from 'react';
import * as echarts from 'echarts/core';
import type { EChartsCoreOption } from 'echarts/core';
import { BarChart, LineChart } from 'echarts/charts';
import { GridComponent, MarkLineComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([LineChart, BarChart, GridComponent, TooltipComponent, MarkLineComponent, CanvasRenderer]);

export const CHART = { text: '#8495bf', grid: '#16213f', axis: '#26365f', cyan: '#3db4ff', green: '#2fe39a', amber: '#ffb02e', red: '#ff4d5e' };

export function Chart({ option, height }: { option: EChartsCoreOption; height: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const inst = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const chart = echarts.init(el, undefined, { renderer: 'canvas' });
    inst.current = chart;
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(el);
    return () => {
      ro.disconnect();
      chart.dispose();
      inst.current = null;
    };
  }, []);

  useEffect(() => {
    inst.current?.setOption(option, { notMerge: false, lazyUpdate: true });
  }, [option]);

  return <div ref={ref} style={{ height, width: '100%' }} />;
}
