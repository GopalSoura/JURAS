import type { ReactNode } from 'react';
import { useStore } from '../store';
import type { ModuleId } from '../types';
import { BuildingCard, FeedCard, Kpis, RoutesCard, SafetyCard, StormCard } from './cards';

const ORDER: Record<ModuleId, ReactNode[]> = {
  overview: [<Kpis key="k" />, <RoutesCard key="r" />, <SafetyCard key="s" />, <BuildingCard key="b" />, <StormCard key="w" />, <FeedCard key="f" />],
  fire: [<RoutesCard key="r" />, <Kpis key="k" />, <SafetyCard key="s" />, <FeedCard key="f" />],
  structure: [<BuildingCard key="b" />, <Kpis key="k" />, <SafetyCard key="s" />, <FeedCard key="f" />],
  flood: [<StormCard key="w" />, <RoutesCard key="r" />, <Kpis key="k" />, <FeedCard key="f" />],
  routing: [<RoutesCard key="r" />, <StormCard key="w" />, <Kpis key="k" />],
  sensors: [<FeedCard key="f" />, <Kpis key="k" />, <StormCard key="w" />, <BuildingCard key="b" />],
};

export function OverviewPanel({ className = '' }: { className?: string }) {
  const module = useStore((s) => s.module);
  return (
    <aside className={`panel min-h-0 flex-col border-y-0 border-r-0 ${className}`} aria-label="Overview">
      <div className="border-b border-line px-3 py-2.5">
        <span className="label">Overview</span>
      </div>
      <div className="scroll min-h-0 flex-1 space-y-2.5 p-2.5">{ORDER[module]}</div>
    </aside>
  );
}
