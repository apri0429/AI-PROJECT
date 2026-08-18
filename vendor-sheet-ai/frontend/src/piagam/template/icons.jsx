import MenuRoundedIcon from '@mui/icons-material/MenuRounded'
import NotificationsNoneRoundedIcon from '@mui/icons-material/NotificationsNoneRounded'
import RefreshRoundedIcon from '@mui/icons-material/RefreshRounded'
import SearchRoundedIcon from '@mui/icons-material/SearchRounded'
import CloseRoundedIcon from '@mui/icons-material/CloseRounded'
import KeyboardArrowDownRoundedIcon from '@mui/icons-material/KeyboardArrowDownRounded'
import ChevronLeftRoundedIcon from '@mui/icons-material/ChevronLeftRounded'
import ChevronRightRoundedIcon from '@mui/icons-material/ChevronRightRounded'

function createIconComponent(IconComponent) {
  return function WrappedIcon({ size = 20, className, style, ...props }) {
    return (
      <span
        className={className}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
          lineHeight: 0,
          ...style,
        }}
      >
        <IconComponent sx={{ fontSize: size, display: 'block' }} {...props} />
      </span>
    )
  }
}

export const Menu01 = createIconComponent(MenuRoundedIcon)
export const Bell04 = createIconComponent(NotificationsNoneRoundedIcon)
export const RefreshCw05 = createIconComponent(RefreshRoundedIcon)
export const SearchMd = createIconComponent(SearchRoundedIcon)
export const XClose = createIconComponent(CloseRoundedIcon)
export const ChevronDown = createIconComponent(KeyboardArrowDownRoundedIcon)
export const ChevronLeft = createIconComponent(ChevronLeftRoundedIcon)
export const ChevronRight = createIconComponent(ChevronRightRoundedIcon)
