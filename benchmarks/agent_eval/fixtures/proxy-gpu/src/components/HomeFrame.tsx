import type { ReactNode } from 'react';
import type { SiteContent } from '../lib/content/schema';

export interface HomeFrameProps {
  site: SiteContent;
  avatar: string;
  scene?: ReactNode;
  music?: ReactNode;
}

export function HomeFrame({ site, avatar, scene, music }: HomeFrameProps) {
  return (
    <div className="home-frame" data-testid="home-frame">
      <a className="skip-link" href="#scene-panel">
        Skip to the scene
      </a>
      <aside
        className="profile-nav"
        aria-label="Personal navigation"
        data-layout="navigation"
      >
        <img
          className="profile-avatar"
          src={avatar}
          width={72}
          height={72}
          alt={`${site.name}'s avatar`}
        />
        <nav aria-label="External links">
          {site.links.map((link) => (
            <a
              key={link.href}
              href={link.href}
              target="_blank"
              rel="noreferrer"
            >
              {link.label}
            </a>
          ))}
        </nav>
      </aside>
      <main
        id="scene-panel"
        className="scene-panel"
        tabIndex={-1}
        aria-label="Interactive scenes"
        data-layout="scene"
      >
        <h1 className="sr-only">{site.title}</h1>
        {scene}
      </main>
      <footer className="bottom-bar" data-layout="footer">
        <div className="music-slot" data-layout="music">
          {music}
        </div>
        <div className="legal-links" data-layout="legal">
          {site.registrations.map((link) => (
            <a
              key={link.href}
              href={link.href}
              target="_blank"
              rel="noreferrer"
            >
              {link.label}
            </a>
          ))}
        </div>
      </footer>
    </div>
  );
}
