import { useEffect, useState } from 'react';
import { useStore } from './store';
import { feed } from './lib/feed';
import { TopBar } from './components/TopBar';
import { AlertsPanel } from './components/AlertsPanel';
import { OverviewPanel } from './components/OverviewPanel';
import { MapView } from './components/MapView';
import { BottomNav } from './components/BottomNav';
import { SimBar } from './components/SimBar';
import { Icon } from './components/icons';

type Tab = 'alerts' | 'map' | 'overview';

export default function App() {
  const [tab, setTab] = useState<Tab>('map');

  useEffect(() => {
    const st = useStore.getState();
    st.setFeed('connecting', feed.label);
    feed.start(
      (m) => useStore.getState().apply(m),
      (s) => useStore.getState().setFeed(s, feed.label),
    );
    const iv = setInterval(() => useStore.getState().sample(), 2000);
    return () => {
      feed.stop();
      clearInterval(iv);
    };
  }, []);

  const show = (t: Tab) => (tab === t ? 'flex' : 'hidden');
  const tabBtn = (t: Tab, label: string, icon: 'bell' | 'cube' | 'grid') => (
    <button
      key={t}
      onClick={() => setTab(t)}
      aria-current={tab === t ? 'page' : undefined}
      className={`flex flex-1 flex-col items-center gap-0.5 py-1.5 text-[11px] ${tab === t ? 'text-cyan' : 'text-dim'}`}
    >
      <Icon name={icon} size={18} />
      {label}
    </button>
  );

  return (
    <div className="flex h-full flex-col">
      <TopBar />
      <main className="relative flex min-h-0 flex-1 lg:grid lg:grid-cols-[340px_minmax(0,1fr)_376px]">
        <AlertsPanel className={`${show('alerts')} w-full lg:flex lg:w-auto`} />
        <div className={`${show('map')} relative min-h-0 min-w-0 flex-1 lg:flex`}>
          <MapView />
          <SimBar />
          <BottomNav className="bottom-3" />
        </div>
        <OverviewPanel className={`${show('overview')} w-full lg:flex lg:w-auto`} />
      </main>
      <div className="panel flex shrink-0 border-x-0 border-b-0 pb-[env(safe-area-inset-bottom,0px)] lg:hidden">
        {tabBtn('alerts', 'Alerts', 'bell')}
        {tabBtn('map', 'Map', 'cube')}
        {tabBtn('overview', 'Overview', 'grid')}
      </div>
    </div>
  );
}
