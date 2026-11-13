const PATHS = {
  grid: 'M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z',
  flame: 'M12 3c1 3 4.5 5 4.5 9.5a4.5 4.5 0 0 1-9 0c0-2 1-3.2 2-4.2 0 2 1 2.4 2 2.4-.6-3 .2-4.6.5-7.7z',
  building: 'M5 21V5l8-2v18M13 8h6v13M8 8h2M8 12h2M8 16h2M16 12h1M16 16h1M3 21h18',
  drop: 'M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z',
  route: 'M6 3a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM18 17a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM8 5h6a3 3 0 0 1 0 6h-4a3 3 0 0 0 0 6h6',
  radio: 'M12 10.5a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3zM8.3 8.3a5 5 0 0 0 0 7.4M15.7 8.3a5 5 0 0 1 0 7.4M5.5 5.5a9 9 0 0 0 0 13M18.5 5.5a9 9 0 0 1 0 13',
  bell: 'M6 16v-5a6 6 0 0 1 12 0v5l1.5 2h-15zM10 20a2 2 0 0 0 4 0',
  plus: 'M12 5v14M5 12h14',
  minus: 'M5 12h14',
  cube: 'M12 3l8 4.5v9L12 21l-8-4.5v-9zM12 12l8-4.5M12 12v9M12 12L4 7.5',
  layers: 'M12 3l9 5-9 5-9-5zM3 13l9 5 9-5',
  compass: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM15.5 8.5l-2 5-5 2 2-5z',
  check: 'M5 12.5l4.5 4.5L19 7.5',
  play: 'M7 5l11 7-11 7z',
  reset: 'M4 12a8 8 0 1 1 3 6.2M4 19v-5h5',
  crack: 'M12 3l-2 6 4 3-3 4 2 5',
  warn: 'M12 4l9 16H3zM12 10v4M12 17v.5',
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 18, className }: { name: IconName; size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d={PATHS[name]} />
    </svg>
  );
}

export const FLAME_SVG =
  '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3c1 3 4.5 5 4.5 9.5a4.5 4.5 0 0 1-9 0c0-2 1-3.2 2-4.2 0 2 1 2.4 2 2.4-.6-3 .2-4.6.5-7.7z"/></svg>';
