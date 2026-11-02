import { site } from '../../lib/content/load';
import { DockIcon } from './DockIcon';

export type RailStudy = 'glide' | 'tether' | 'relay';

export function ElsewhereRails({ study }: { study: RailStudy }) {
  return (
    <div
      className="orbit-ribbon-copy orbit-elsewhere orbit-rails"
      data-rail-study={study}
    >
      <nav aria-label="Elsewhere">
        {site.links.map((link) => {
          const icon = link.label === 'GitHub' ? 'repository' : 'journal';
          return (
            <a
              href={link.href}
              key={link.href}
              className="orbit-rail-link"
              aria-label={link.label}
              title={link.label}
            >
              <span className="orbit-rail-axis" aria-hidden="true">
                <span className="orbit-rail-window">
                  <span className="orbit-rail-label">
                    <DockIcon name={icon} />
                    <span>{link.label}</span>
                  </span>
                  {study === 'relay' && (
                    <span className="orbit-rail-label orbit-rail-echo">
                      <DockIcon name={icon} />
                      <span>{link.label}</span>
                    </span>
                  )}
                </span>
                <span className="orbit-rail-line" />
              </span>
            </a>
          );
        })}
      </nav>
    </div>
  );
}
