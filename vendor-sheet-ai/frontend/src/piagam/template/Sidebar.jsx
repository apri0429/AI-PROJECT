import { useMemo, useState } from 'react'

import { ChevronLeft, ChevronRight, XClose } from './icons.jsx'
import {
  defaultNavigationPath,
  implementedNavigationPaths,
  primaryNavigationItems,
  secondaryNavigationItems,
} from '../../services/templateServices/Navigation.js'
import '../../styles/templateStyle/TemplateComponents.css'

function getInitials(name) {
  return name
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('')
}

function getItemKey(item) {
  return item.id ?? item.href ?? item.label
}

function getGroupKey(item) {
  return `group:${getItemKey(item)}`
}

function isItemActive(item, currentPath) {
  if (item.href === currentPath) {
    return true
  }

  return item.children?.some((child) => isItemActive(child, currentPath)) ?? false
}

function getInitiallyExpandedGroups(items, currentPath) {
  return items.reduce((expandedGroups, item) => {
    if (item.children?.length && isItemActive(item, currentPath)) {
      expandedGroups[getGroupKey(item)] = true
    }

    if (item.children?.length) {
      Object.assign(expandedGroups, getInitiallyExpandedGroups(item.children, currentPath))
    }

    return expandedGroups
  }, {})
}

function SidebarNavItem({
  item,
  selectedPath,
  collapsed,
  onSelect,
  expandedGroups,
  onToggleGroup,
  depth = 0,
}) {
  const Icon = item.icon
  const hasChildren = item.children?.length > 0
  const active = isItemActive(item, selectedPath)
  const expanded = hasChildren ? expandedGroups[getGroupKey(item)] ?? false : false
  const isButton = hasChildren || !item.href
  const submenuId = hasChildren ? `${getGroupKey(item)}-submenu` : undefined
  const className = [
    'nav-item',
    active ? 'active' : '',
    hasChildren ? 'nav-item--accordion' : '',
    expanded ? 'nav-item--expanded' : '',
    isButton ? 'nav-item--button' : '',
    depth > 0 ? 'nav-item--child' : '',
    item.variant === 'danger' ? 'logout-item' : '',
  ]
    .filter(Boolean)
    .join(' ')

  const content = (
    <>
      {Icon ? (
        <Icon className="nav-icon" size={22} />
      ) : (
        <span className="nav-item__bullet" aria-hidden="true" />
      )}
      <span className="nav-text">{item.label}</span>
      {hasChildren ? <ChevronRight className="nav-item__chevron" size={18} /> : null}
    </>
  )

  const handleClick = (event) => {
    if (hasChildren) {
      event.preventDefault()
      onToggleGroup?.(item)
      return
    }

    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) {
      return
    }

    event.preventDefault()
    onSelect?.(item)
  }

  return (
    <>
      {isButton ? (
        <button
          type="button"
          className={className}
          data-tooltip={collapsed ? item.label : undefined}
          aria-controls={submenuId}
          aria-current={active && !hasChildren ? 'page' : undefined}
          aria-expanded={hasChildren ? expanded : undefined}
          onClick={handleClick}
        >
          {content}
        </button>
      ) : (
        <a
          href={item.href}
          className={className}
          data-tooltip={collapsed ? item.label : undefined}
          aria-current={active ? 'page' : undefined}
          onClick={handleClick}
        >
          {content}
        </a>
      )}

      {hasChildren && !collapsed ? (
        <div
          id={submenuId}
          className={`nav-submenu${expanded ? ' expanded' : ''}`}
          aria-hidden={!expanded}
        >
          {item.children.map((child) => (
            <SidebarNavItem
              key={getItemKey(child)}
              item={child}
              selectedPath={selectedPath}
              collapsed={collapsed}
              onSelect={onSelect}
              expandedGroups={expandedGroups}
              onToggleGroup={onToggleGroup}
              depth={depth + 1}
            />
          ))}
        </div>
      ) : null}
    </>
  )
}

function Sidebar({
  collapsed = false,
  mobileOpen = false,
  activePath = '/dashboard',
  userName = 'Al fatih',
  userRole = 'Frontend Developer',
  primaryItems = primaryNavigationItems,
  secondaryItems = secondaryNavigationItems,
  onAction,
  onToggleCollapse,
  onCloseMobile,
}) {
  const [expandedGroups, setExpandedGroups] = useState({})
  const initials = getInitials(userName)
  const activeExpandedGroups = useMemo(
    () => getInitiallyExpandedGroups([...primaryItems, ...secondaryItems], activePath),
    [activePath, primaryItems, secondaryItems],
  )
  const visibleExpandedGroups = useMemo(
    () => ({
      ...expandedGroups,
      ...activeExpandedGroups,
    }),
    [activeExpandedGroups, expandedGroups],
  )

  const handleSelect = async (item) => {
    if (item.external && item.href) {
      if (mobileOpen) {
        onCloseMobile?.()
      }

      window.location.assign(item.href)
      return
    }

    if (item.action) {
      onAction?.(item.action, item)

      if (mobileOpen) {
        onCloseMobile?.()
      }

      return
    }

    if (!item.href) {
      return
    }

    if (item.href && implementedNavigationPaths.includes(item.href)) {
      const nextPath = item.href || defaultNavigationPath

      if (window.location.pathname !== nextPath) {
        window.history.pushState({}, '', nextPath)
        window.dispatchEvent(new PopStateEvent('popstate'))
      }
    }

    if (mobileOpen) {
      onCloseMobile?.()
    }
  }

  const handleToggleGroup = (item) => {
    const groupKey = getGroupKey(item)

    if (collapsed) {
      setExpandedGroups((currentGroups) => ({
        ...currentGroups,
        [groupKey]: true,
      }))
      onToggleCollapse?.()
      return
    }

    setExpandedGroups((currentGroups) => ({
      ...currentGroups,
      [groupKey]: !(currentGroups[groupKey] ?? false),
    }))
  }

  const sidebarClassName = [
    'sidebar',
    collapsed ? 'collapsed' : '',
    mobileOpen ? 'mobile-open' : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <aside id="sidebar" className={sidebarClassName}>
      <button
        type="button"
        className="sidebar-toggle"
        aria-label="Toggle Sidebar"
        onClick={onToggleCollapse}
      >
        {collapsed ? (
          <ChevronRight className="toggle-icon" size={16} />
        ) : (
          <ChevronLeft className="toggle-icon" size={16} />
        )}
      </button>

      <button
        type="button"
        className="sidebar-mobile-dismiss"
        aria-label="Close Sidebar"
        onClick={onCloseMobile}
      >
        <XClose size={18} />
      </button>

      <div className="sidebar-logo">
        <div className="profile-content">
          <div className="profile-avatar">
            <span className="profile-avatar__badge">{initials}</span>
            <div className="online-status" />
          </div>

          <div className="profile-info">
            <h3 className="profile-name">{userName}</h3>
            <p className="profile-role">{userRole}</p>
          </div>
        </div>
      </div>

      <nav className="sidebar-nav" aria-label="Main navigation">
        {primaryItems.map((item) => (
          <SidebarNavItem
            key={getItemKey(item)}
            item={item}
            selectedPath={activePath}
            collapsed={collapsed}
            onSelect={handleSelect}
            expandedGroups={visibleExpandedGroups}
            onToggleGroup={handleToggleGroup}
          />
        ))}
      </nav>

      <div className="sidebar-bottom">
        {secondaryItems.map((item) => (
          <SidebarNavItem
            key={getItemKey(item)}
            item={item}
            selectedPath={activePath}
            collapsed={collapsed}
            onSelect={handleSelect}
            expandedGroups={visibleExpandedGroups}
            onToggleGroup={handleToggleGroup}
          />
        ))}
      </div>

      <div className="sidebar-copyright" aria-label="Copyright">
        <p>&copy; 2026 PT Pilar Niaga Makmur</p>
        <p>Developed by IT Team </p>
      </div>
    </aside>
  )
}

export default Sidebar
