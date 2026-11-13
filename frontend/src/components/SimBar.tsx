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
  const run = (name: Extract<ClientCmd, { cmd: 'scenario' }>['name']) => feed.send({ cmd: 'scenario', name });
  return (
    <div className={`panel absolute left-3 top-3 z-10 max-w-[calc(100%-5rem)] rounded-md p-2 ${className}`}>
      <div className="mb-1.5 flex items-center gap-1.5">
        <Icon name="radio" size={14} className="text-cyan" />
        <span className="label">{status === 'sim' ? 'Hardware simulator' : 'Scenario commands'}</span>
      </div>
      <div className="flex flex-wrap gap-1">
        {BTN.map((b) => (
          <button key={b.name} className="btn flex items-center gap-1 px-2 py-1 text-[12px]" onClick={() => run(b.name)}>
            <Icon name={b.icon} size={13} />
            {b.label}
          </button>
        ))}
      </div>
      <p className="mt-1.5 hidden max-w-[260px] text-[10.5px] leading-snug text-dim sm:block">
        Injects readings the same way an ESP32 node would. The backend path is unchanged.
      </p>
    </div>
  );
}
