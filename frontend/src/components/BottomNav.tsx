import { useStore } from '../store';
import { NAV } from '../lib/meta';
import type { ModuleId } from '../types';
import { Icon, type IconName } from './icons';

const ICON: Record<ModuleId, IconName> = { overview: 'grid', fire: 'flame', structure: 'building', flood: 'drop', routing: 'route', sensors: 'radio' };

export function BottomNav({ className = '' }: { className?: string }) {
  const module = useStore((s) => s.module);
  const setModule = useStore((s) => s.setModule);
  return (
    <nav className={`panel absolute left-1/2 z-10 flex max-w-[calc(100%-1.5rem)] -translate-x-1/2 gap-0.5 overflow-x-auto rounded-xl p-1 ${className}`} aria-label="Modules">
      {NAV.map((n) => {
        const on = n.id === module;
        return (
          <button
            key={n.id}
            onClick={() => setModule(n.id)}
            aria-current={on ? 'page' : undefined}
            className={`flex min-w-[64px] flex-col items-center gap-0.5 rounded-lg px-2.5 py-1.5 text-[11px] transition-colors ${on ? 'bg-[#16346a] text-cyan' : 'text-dim hover:bg-[#16213f] hover:text-ink'}`}
            style={on ? { boxShadow: 'inset 0 0 0 1px #3db4ff88, 0 0 14px rgba(61,180,255,.25)' } : undefined}
          >
            <Icon name={ICON[n.id]} size={18} />
            {n.label}
          </button>
        );
      })}
    </nav>
  );
}
