import { site } from '../../lib/content/load';
import { DockIcon } from './DockIcon';

export function RegistrationLinks({ docked = false }: { docked?: boolean }) {
  return (
    <footer
      className={`orbit-footer${docked ? ' orbit-dock-registrations' : ''}`}
      aria-label="Website registrations"
    >
      {site.registrations.map((registration) => (
        <a key={registration.href} href={registration.href}>
          {docked && <DockIcon name="shield" />}
          <span>{registration.label}</span>
        </a>
      ))}
    </footer>
  );
}
