function IconBase({ size = 20, className, children, ...props }) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      {children}
    </svg>
  )
}

export function Bell04(props) {
  return (
    <IconBase {...props}>
      <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" />
      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </IconBase>
  )
}

export function ChevronDown(props) {
  return (
    <IconBase {...props}>
      <path d="m6 9 6 6 6-6" />
    </IconBase>
  )
}

export function ChevronLeft(props) {
  return (
    <IconBase {...props}>
      <path d="m15 18-6-6 6-6" />
    </IconBase>
  )
}

export function ChevronRight(props) {
  return (
    <IconBase {...props}>
      <path d="m9 18 6-6-6-6" />
    </IconBase>
  )
}

export function Calendar01(props) {
  return (
    <IconBase {...props}>
      <path d="M8 2v4" />
      <path d="M16 2v4" />
      <rect x="3" y="4" width="18" height="18" rx="2" />
      <path d="M3 10h18" />
      <path d="M8 14h.01" />
      <path d="M12 14h.01" />
      <path d="M16 14h.01" />
      <path d="M8 18h.01" />
      <path d="M12 18h.01" />
    </IconBase>
  )
}

export function Edit03(props) {
  return (
    <IconBase {...props}>
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z" />
    </IconBase>
  )
}

export function FileText01(props) {
  return (
    <IconBase {...props}>
      <path d="M14 2H7a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7z" />
      <path d="M14 2v5h5" />
      <path d="M9 13h6" />
      <path d="M9 17h6" />
      <path d="M9 9h1" />
    </IconBase>
  )
}

export function LayoutDashboard(props) {
  return (
    <IconBase {...props}>
      <rect x="3" y="3" width="7" height="8" rx="1.5" />
      <rect x="14" y="3" width="7" height="5" rx="1.5" />
      <rect x="14" y="12" width="7" height="9" rx="1.5" />
      <rect x="3" y="15" width="7" height="6" rx="1.5" />
    </IconBase>
  )
}

export function LogOut01(props) {
  return (
    <IconBase {...props}>
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <path d="m16 17 5-5-5-5" />
      <path d="M21 12H9" />
    </IconBase>
  )
}

export function LogOutLeft01(props) {
  return (
    <IconBase {...props}>
      <path d="M15 21h4a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2h-4" />
      <path d="m8 17-5-5 5-5" />
      <path d="M3 12h12" />
    </IconBase>
  )
}

export function Menu01(props) {
  return (
    <IconBase {...props}>
      <path d="M4 6h16" />
      <path d="M4 12h16" />
      <path d="M4 18h16" />
    </IconBase>
  )
}

export function RefreshCw05(props) {
  return (
    <IconBase {...props}>
      <path d="M21 12a9 9 0 0 1-15.3 6.36L3 15" />
      <path d="M3 21v-6h6" />
      <path d="M3 12a9 9 0 0 1 15.3-6.36L21 9" />
      <path d="M21 3v6h-6" />
    </IconBase>
  )
}

export function SearchMd(props) {
  return (
    <IconBase {...props}>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </IconBase>
  )
}

export function Settings01(props) {
  return (
    <IconBase {...props}>
      <path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06A1.65 1.65 0 0 0 15 19.4a1.65 1.65 0 0 0-1 .6 1.65 1.65 0 0 0-.4 1.1V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 8 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 3.6 15a1.65 1.65 0 0 0-.6-1 1.65 1.65 0 0 0-1.1-.4H2a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 3.6 8a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 8 3.6a1.65 1.65 0 0 0 1-.6 1.65 1.65 0 0 0 .4-1.1V2a2 2 0 1 1 4 0v.09A1.65 1.65 0 0 0 15 3.6a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 8c.16.38.38.72.6 1 .3.25.69.4 1.1.4H21a2 2 0 1 1 0 4h-.09A1.65 1.65 0 0 0 19.4 15" />
    </IconBase>
  )
}

export function Ticket01(props) {
  return (
    <IconBase {...props}>
      <path d="M3 9a3 3 0 0 0 0 6v3a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-3a3 3 0 0 0 0-6V6a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2z" />
      <path d="M13 5v2" />
      <path d="M13 17v2" />
      <path d="M13 11v2" />
    </IconBase>
  )
}

export function Trash03(props) {
  return (
    <IconBase {...props}>
      <path d="M3 6h18" />
      <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
      <path d="M19 6 18 20a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
      <path d="M10 11v6" />
      <path d="M14 11v6" />
    </IconBase>
  )
}

export function Users01(props) {
  return (
    <IconBase {...props}>
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </IconBase>
  )
}

export function Table01(props) {
  return (
    <IconBase {...props}>
      <path d="M3 5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5z" />
      <path d="M3 9h18" />
      <path d="M3 15h18" />
      <path d="M9 9v12" />
      <path d="M15 9v12" />
    </IconBase>
  )
}

export function Chart01(props) {
  return (
    <IconBase {...props}>
      <path d="M3 3v18h18" />
      <rect x="7" y="12" width="3" height="6" rx="1" />
      <rect x="12" y="8" width="3" height="10" rx="1" />
      <rect x="17" y="5" width="3" height="13" rx="1" />
    </IconBase>
  )
}

export function XClose(props) {
  return (
    <IconBase {...props}>
      <path d="M18 6 6 18" />
      <path d="m6 6 12 12" />
    </IconBase>
  )
}

export function MessageCircle01(props) {
  return (
    <IconBase {...props}>
      <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5Z" />
    </IconBase>
  )
}

export function Image01(props) {
  return (
    <IconBase {...props}>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <circle cx="9" cy="10" r="1.5" fill="currentColor" stroke="none" />
      <path d="m4 17 5-5 3.5 3.5L16 12l4 5" />
    </IconBase>
  )
}

export function Languages01(props) {
  return (
    <IconBase {...props}>
      <path d="M3.5 5.5h9M7.5 3.5v2M5 8c.8 1.7 2.2 3.1 4.4 4.3M11 6.5C10.3 8.9 8.5 11.3 5.5 13.5" />
      <path d="M12.5 20 16 11l3.5 9M13.5 17h5" />
    </IconBase>
  )
}

export function AlignLeft01(props) {
  return (
    <IconBase {...props}>
      <path d="M4 6h16M4 12h10M4 18h13" />
    </IconBase>
  )
}

export function Clock01(props) {
  return (
    <IconBase {...props}>
      <circle cx="12" cy="12" r="8.25" />
      <path d="M12 7.5V12l3.25 2" />
    </IconBase>
  )
}

export function Archive01(props) {
  return (
    <IconBase {...props}>
      <path d="M4.75 8.25h14.5M6 8.25v10c0 .97.78 1.75 1.75 1.75h8.5c.97 0 1.75-.78 1.75-1.75v-10M5.75 4h12.5c.69 0 1.25.56 1.25 1.25v3H4.5v-3C4.5 4.56 5.06 4 5.75 4ZM9.5 12h5" />
    </IconBase>
  )
}

export function SquarePen01(props) {
  return (
    <IconBase {...props}>
      <path d="M12 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
      <path d="M18.38 2.62a1.98 1.98 0 1 1 2.8 2.8L11.4 15.19a2 2 0 0 1-.85.51l-2.87.84a.5.5 0 0 1-.62-.62l.84-2.87a2 2 0 0 1 .51-.85z" />
    </IconBase>
  )
}
