/**
 * The icon set, as inline SVG.
 *
 * No icon dependency. Janus needs about thirty glyphs and an icon package is
 * several megabytes of them, tree-shaken imperfectly, for a deployment whose
 * stated goal is to be small. These are drawn on a 24-grid with a 1.75 stroke,
 * which is the weight that holds up at the 14–16px they are actually rendered
 * at — 1.5 goes spindly and 2 goes heavy beside 13px text.
 *
 * Every icon takes `className` only. Size and colour come from the caller
 * through `w-*`/`h-*` and `currentColor`, so an icon never has to be edited to
 * be used somewhere new.
 */

import type { ReactNode } from 'react'

type IconProps = { className?: string }

function svg(children: ReactNode) {
  return function Icon({ className = 'h-4 w-4' }: IconProps) {
    return (
      <svg
        className={className}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.75}
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        {children}
      </svg>
    )
  }
}

/* -- navigation --------------------------------------------------------- */

export const IconOverview = svg(
  <>
    <rect x="3" y="3" width="7" height="9" rx="1.5" />
    <rect x="14" y="3" width="7" height="5" rx="1.5" />
    <rect x="14" y="12" width="7" height="9" rx="1.5" />
    <rect x="3" y="16" width="7" height="5" rx="1.5" />
  </>,
)

/** The gateway itself: a doorway. Janus is the god of gates. */
export const IconGateway = svg(
  <>
    <path d="M4 21V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v15" />
    <path d="M2 21h20" />
    <path d="M9 21v-6a3 3 0 0 1 6 0v6" />
  </>,
)

export const IconRoute = svg(
  <>
    <circle cx="5" cy="6" r="2.5" />
    <circle cx="19" cy="18" r="2.5" />
    <path d="M7.5 6h6a3.5 3.5 0 0 1 0 7h-3a3.5 3.5 0 0 0 0 7h6" />
  </>,
)

export const IconUpstream = svg(
  <>
    <rect x="3" y="3" width="18" height="6" rx="1.5" />
    <rect x="3" y="15" width="18" height="6" rx="1.5" />
    <path d="M7 9v6M17 9v6" />
    <path d="M6.5 6h.01M6.5 18h.01" />
  </>,
)

export const IconDomain = svg(
  <>
    <circle cx="12" cy="12" r="9" />
    <path d="M3 12h18" />
    <path d="M12 3a14 14 0 0 1 0 18a14 14 0 0 1 0-18Z" />
  </>,
)

export const IconConfig = svg(
  <>
    <path d="M4 6h16M4 12h16M4 18h10" />
    <circle cx="17" cy="18" r="2.5" />
  </>,
)

export const IconChart = svg(
  <>
    <path d="M3 21h18" />
    <path d="M6 21V10M11 21V4M16 21v-7M21 21v-11" />
  </>,
)

export const IconPulse = svg(<path d="M2 12h4l3-8 4 16 3-8h6" />)

export const IconError = svg(
  <>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v6M12 16.5v.01" />
  </>,
)

export const IconGauge = svg(
  <>
    <path d="M4 18a9 9 0 1 1 16 0" />
    <path d="M12 18l4.5-5" />
  </>,
)

export const IconBandwidth = svg(
  <>
    <path d="M3 7h13l-3-3M21 17H8l3 3" />
  </>,
)

export const IconShield = svg(
  <>
    <path d="M12 3l7 3v6c0 4.5-3 8.2-7 9-4-.8-7-4.5-7-9V6l7-3Z" />
    <path d="M9.5 12l1.8 1.8 3.4-3.6" />
  </>,
)

export const IconClients = svg(
  <>
    <circle cx="9" cy="8" r="3" />
    <path d="M3.5 20a5.5 5.5 0 0 1 11 0" />
    <path d="M16 5.5a3 3 0 0 1 0 5.8M17.5 20a5.5 5.5 0 0 0-2.2-4.4" />
  </>,
)

export const IconBlock = svg(
  <>
    <circle cx="12" cy="12" r="9" />
    <path d="M5.6 5.6l12.8 12.8" />
  </>,
)

export const IconAllow = svg(
  <>
    <circle cx="12" cy="12" r="9" />
    <path d="M8 12.2l2.6 2.6L16 9.5" />
  </>,
)

export const IconThrottle = svg(
  <>
    <path d="M12 3v4M12 17v4M3 12h4M17 12h4" />
    <circle cx="12" cy="12" r="4" />
  </>,
)

export const IconKey = svg(
  <>
    <circle cx="8" cy="14" r="4" />
    <path d="M11 11l8-8M17 5l2 2M15 7l2 2" />
  </>,
)

export const IconPolicy = svg(
  <>
    <path d="M6 3h9l4 4v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" />
    <path d="M14 3v5h5" />
    <path d="M9 13h6M9 17h4" />
  </>,
)

export const IconPuzzle = svg(
  <>
    <path d="M10 4h4a1 1 0 0 1 1 1v1.5a1.5 1.5 0 1 0 3 0V5a1 1 0 0 1 1-1h0a1 1 0 0 1 1 1v4a1 1 0 0 1-1 1h-1.5a1.5 1.5 0 1 0 0 3H19a1 1 0 0 1 1 1v4a1 1 0 0 1-1 1h-4" />
    <path d="M10 4a1 1 0 0 0-1 1v1.5a1.5 1.5 0 1 1-3 0V5a1 1 0 0 0-1-1 1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h10" />
  </>,
)

export const IconUsers = svg(
  <>
    <circle cx="12" cy="8" r="3.5" />
    <path d="M5 20a7 7 0 0 1 14 0" />
  </>,
)

export const IconRoles = svg(
  <>
    <circle cx="12" cy="7" r="3" />
    <path d="M6 20v-1a6 6 0 0 1 12 0v1" />
    <path d="M16.5 3.5l1.2 1.2 2.3-2.3" />
  </>,
)

export const IconAudit = svg(
  <>
    <path d="M5 4h11l3 3v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1Z" />
    <path d="M8 10h8M8 14h8M8 18h5" />
  </>,
)

export const IconDeploy = svg(
  <>
    <path d="M12 3v13" />
    <path d="M8 7l4-4 4 4" />
    <path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
  </>,
)

export const IconHeart = svg(
  <>
    <circle cx="12" cy="12" r="9" />
    <path d="M8 12.5l2 2 5-5" />
  </>,
)

export const IconBook = svg(
  <>
    <path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H19v14H5.5A1.5 1.5 0 0 0 4 19.5v-14Z" />
    <path d="M4 19.5A1.5 1.5 0 0 1 5.5 18H19v2H5.5A1.5 1.5 0 0 1 4 19.5Z" />
    <path d="M8 8.5h7M8 12h5" />
  </>,
)

export const IconSettings = svg(
  <>
    <circle cx="12" cy="12" r="3" />
    <path d="M12 2v2.5M12 19.5V22M4.2 4.2l1.8 1.8M18 18l1.8 1.8M2 12h2.5M19.5 12H22M4.2 19.8L6 18M18 6l1.8-1.8" />
  </>,
)

/* -- controls ----------------------------------------------------------- */

export const IconSearch = svg(
  <>
    <circle cx="11" cy="11" r="6.5" />
    <path d="M16 16l4.5 4.5" />
  </>,
)

export const IconClose = svg(<path d="M6 6l12 12M18 6L6 18" />)
export const IconPlus = svg(<path d="M12 5v14M5 12h14" />)
export const IconChevronDown = svg(<path d="M6 9l6 6 6-6" />)
export const IconChevronRight = svg(<path d="M9 6l6 6-6 6" />)
export const IconExternal = svg(
  <>
    <path d="M14 4h6v6" />
    <path d="M20 4l-9 9" />
    <path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
  </>,
)
export const IconWarning = svg(
  <>
    <path d="M10.3 3.9 2.6 17.2A2 2 0 0 0 4.3 20h15.4a2 2 0 0 0 1.7-2.8L13.7 3.9a2 2 0 0 0-3.4 0Z" />
    <path d="M12 9v4M12 16.5v.01" />
  </>,
)
export const IconCheck = svg(<path d="M4 12.5l5 5L20 6.5" />)
export const IconCopy = svg(
  <>
    <rect x="9" y="9" width="12" height="12" rx="2" />
    <path d="M15 5H5a2 2 0 0 0-2 2v10" />
  </>,
)
export const IconRefresh = svg(
  <>
    <path d="M20 12a8 8 0 1 1-2.6-5.9" />
    <path d="M20 4v5h-5" />
  </>,
)
export const IconSun = svg(
  <>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.2 4.2l1.5 1.5M18.3 18.3l1.5 1.5M2 12h2M20 12h2M4.2 19.8l1.5-1.5M18.3 5.7l1.5-1.5" />
  </>,
)
export const IconMoon = svg(<path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z" />)
export const IconLogout = svg(
  <>
    <path d="M14 20H6a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h8" />
    <path d="M17 8l4 4-4 4M21 12H10" />
  </>,
)
export const IconUser = svg(
  <>
    <circle cx="12" cy="8.5" r="3.5" />
    <path d="M5.5 20a6.5 6.5 0 0 1 13 0" />
  </>,
)
export const IconFilter = svg(<path d="M3 5h18l-7 8v6l-4 2v-8L3 5Z" />)
export const IconClock = svg(
  <>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5.5l3.5 2" />
  </>,
)

/* -- BEACN additions -------------------------------------------------- */

export const IconBell = svg(
  <>
    <path d="M18 9a6 6 0 1 0-12 0c0 4-1.5 5.5-2 6.5h16c-.5-1-2-2.5-2-6.5Z" />
    <path d="M10 19a2 2 0 0 0 4 0" />
  </>,
)
export const IconTopic = svg(
  <>
    <path d="M4 7h16M4 12h16M4 17h10" />
  </>,
)
export const IconStream = svg(
  <>
    <circle cx="5" cy="12" r="1.6" />
    <path d="M9 8.5a7 7 0 0 1 0 7M13 6a11 11 0 0 1 0 12M17 4a15 15 0 0 1 0 16" />
  </>,
)
export const IconProducer = svg(
  <>
    <rect x="4" y="4" width="16" height="16" rx="2" />
    <path d="M8 12h8M12 8v8" />
  </>,
)
export const IconTask = svg(
  <>
    <circle cx="12" cy="12" r="9" />
    <path d="M8 12l3 3 5-6" />
  </>,
)
