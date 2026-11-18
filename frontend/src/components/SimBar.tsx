import { useStore } from '../store';
import { feed } from '../lib/feed';
import type { ClientCmd } from '../types';
import { Icon, type IconName } from './icons';

const BTN: { name: 'fire' | 'crack' | 'flood' | 'reset'; label: string; icon: IconName }[] = [
  { name: 'fire', label: 'Fire', icon: 'flame' },
  { name: 'crack', label: 'Crack drift', icon: 'building' },
  { name: 'flood', label: 'Heavy rain', icon: 'drop' },
  { name: 'reset', label: 'Reset', icon: 'reset' },
];

export function SimBar({ className = '' }: { className?: string }) {
  const status = useStore((s) => s.feedStatus);
  const mode = useStore((s) => s.mode);
  const run = (name: Extract<ClientCmd, { cmd: 'scenario' }>['name']) => feed.send({ cmd: 'scenario', name });
  if (mode === 'realtime') return null;
  return (
    <div className={`panel absolute left-3 top-3 z-10 max-w-[calc(100%-5rem)] p-1.5 ${className}`}>
      <div className="mb-1 flex items-center gap-1.5 px-0.5">
        <Icon name="radio" size={12} className="text-accent" />
        <span className="label">{status === 'sim' ? 'Hardware simulator' : 'Scenario injection'}</span>
      </div>
      <div className="flex flex-wrap gap-1">
        {BTN.map((b) => (
          <button key={b.name} className="btn flex items-center gap-1 px-2 py-1 text-[11.5px]" onClick={() => run(b.name)}>
            <Icon name={b.icon} size={12} />
            {b.label}
          </button>
        ))}
      </div>
    </div>
  );
}
