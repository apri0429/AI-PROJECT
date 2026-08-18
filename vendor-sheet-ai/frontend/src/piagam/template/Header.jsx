import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  Bell04,
  ChevronDown,
  Menu01,
  RefreshCw05,
  SearchMd,
  XClose,
} from './icons.jsx'

import logoPiagam from '../../images/logo-piagam2.png'
import logoPiagamTransparent from '../../images/logo-piagam.png'
import {
  ALL_DEPARTMENTS_FILTER_ID,
  ALL_DEPARTMENTS_FILTER_LABEL,
  getDepartmentFilterOptions,
  getSelectedDepartmentFilterLabel,
} from './departmentFilter.js'
import '../../styles/templateStyle/TemplateComponents.css'

function Header({
  breadcrumb = [
    { label: 'All', href: '#' },
    { label: 'Finance', href: '#', active: true },
    { label: 'Legal', href: '#' },
    { label: 'Product', href: '#' },
  ],
  onMenuToggle,
  notificationProps,
  onRefresh,
  searchProps,
  showMenuButton = false,
  departmentFilterProps,
  toolbarActions = [],
  showBreadcrumbBar = true,
}) {
  const hasSearch = Boolean(searchProps)
  const hasNotification = Boolean(notificationProps)
  const hasToolbarActions = toolbarActions.length > 0
  const [isNotificationModalOpen, setIsNotificationModalOpen] = useState(false)
  const [isDepartmentDropdownOpen, setIsDepartmentDropdownOpen] = useState(false)
  const [departmentDropdownStyle, setDepartmentDropdownStyle] = useState(null)
  const breadcrumbFilterRef = useRef(null)
  const departmentDropdownTriggerRef = useRef(null)
  const departmentDropdownRef = useRef(null)

  const departmentFilterOptions = useMemo(() => {
    if (!departmentFilterProps) {
      return []
    }

    return getDepartmentFilterOptions(departmentFilterProps.departments)
  }, [departmentFilterProps])

  const selectedDepartmentLabel = useMemo(() => {
    if (!departmentFilterProps) {
      return ALL_DEPARTMENTS_FILTER_LABEL
    }

    return getSelectedDepartmentFilterLabel(
      departmentFilterProps.departments,
      departmentFilterProps.selectedDepartmentId,
    )
  }, [departmentFilterProps])

  useEffect(() => {
    if (!isNotificationModalOpen) {
      return undefined
    }

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        setIsNotificationModalOpen(false)
      }
    }

    window.addEventListener('keydown', handleKeyDown)

    return () => {
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [isNotificationModalOpen])

  useEffect(() => {
    if (!isDepartmentDropdownOpen) {
      return undefined
    }

    const handlePointerDown = (event) => {
      if (departmentDropdownTriggerRef.current?.contains(event.target)) {
        return
      }

      if (departmentDropdownRef.current?.contains(event.target)) {
        return
      }

      setIsDepartmentDropdownOpen(false)
    }

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        setIsDepartmentDropdownOpen(false)
      }
    }

    window.addEventListener('mousedown', handlePointerDown)
    window.addEventListener('keydown', handleKeyDown)

    return () => {
      window.removeEventListener('mousedown', handlePointerDown)
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [isDepartmentDropdownOpen])

  useLayoutEffect(() => {
    if (!isDepartmentDropdownOpen) {
      return undefined
    }

    const updateDropdownPosition = () => {
      const triggerElement = departmentDropdownTriggerRef.current

      if (!triggerElement) {
        return
      }

      const triggerBounds = triggerElement.getBoundingClientRect()
      const minimumWidth = 220
      const preferredWidth = Math.max(triggerBounds.width, minimumWidth)
      const viewportWidth = window.innerWidth
      const nextLeft = Math.min(
        triggerBounds.left,
        Math.max(12, viewportWidth - preferredWidth - 12),
      )

      setDepartmentDropdownStyle({
        top: triggerBounds.bottom + 8,
        left: Math.max(12, nextLeft),
        minWidth: preferredWidth,
      })
    }

    updateDropdownPosition()

    window.addEventListener('resize', updateDropdownPosition)
    window.addEventListener('scroll', updateDropdownPosition, true)

    return () => {
      window.removeEventListener('resize', updateDropdownPosition)
      window.removeEventListener('scroll', updateDropdownPosition, true)
    }
  }, [isDepartmentDropdownOpen])

  const departmentDropdownPortal =
    isDepartmentDropdownOpen && typeof document !== 'undefined' && departmentDropdownStyle
      ? createPortal(
          <div
            className="breadcrumb-dropdown breadcrumb-dropdown--floating"
            id="breadcrumb-departments-dropdown"
            role="menu"
            ref={departmentDropdownRef}
            style={departmentDropdownStyle}
          >
            {departmentFilterOptions.map((option) => (
              <button
                key={option.id}
                type="button"
                className={`breadcrumb-dropdown__option${
                  option.id ===
                  (departmentFilterProps.selectedDepartmentId ?? ALL_DEPARTMENTS_FILTER_ID)
                    ? ' active'
                    : ''
                }`}
                onClick={() => {
                  departmentFilterProps.onSelect?.(option.id)
                  setIsDepartmentDropdownOpen(false)
                }}
              >
                <span className="breadcrumb-dropdown__label">{option.label}</span>
              </button>
            ))}
          </div>,
          document.body,
        )
      : null

  const renderBreadcrumb = () => {
    if (!departmentFilterProps) {
      return breadcrumb.map((item, index) => (
        <div className="breadcrumb-item" key={`${item.label}-${index}`}>
          <a
            href={item.href ?? '#'}
            className={`breadcrumb-link${item.active ? ' active' : ''}`}
            onClick={(event) => {
              if (!item.href || item.href === '#') {
                event.preventDefault()
              }
            }}
          >
            {item.label}
          </a>

          {index < breadcrumb.length - 1 ? (
            <span className="breadcrumb-separator">/</span>
          ) : null}
        </div>
      ))
    }

    return (
      <>
        <div className="breadcrumb-item breadcrumb-item--group">
          <div className="breadcrumb-group">
            <button
              ref={departmentDropdownTriggerRef}
              type="button"
              className="breadcrumb-link breadcrumb-link--button active"
              onClick={() => setIsDepartmentDropdownOpen((currentValue) => !currentValue)}
              aria-expanded={isDepartmentDropdownOpen}
              aria-controls="breadcrumb-departments-dropdown"
            >
              <span>{selectedDepartmentLabel}</span>
              <ChevronDown
                size={14}
                aria-hidden="true"
                className={`breadcrumb-dropdown-icon${isDepartmentDropdownOpen ? ' open' : ''}`}
              />
            </button>
          </div>
        </div>

        {departmentFilterProps.isLoading ? (
          <span className="breadcrumb-status">Memuat divisi...</span>
        ) : null}

        {departmentFilterProps.error ? (
          <span className="breadcrumb-status breadcrumb-status--error">
            {departmentFilterProps.error}
          </span>
        ) : null}
      </>
    )
  }

  return (
    <header className="header-main">
      <img
        src={logoPiagamTransparent}
        alt=""
        aria-hidden="true"
        className="header-accent-logo"
      />

      <div className="header-content">
        <div className="header-left">
          {showMenuButton ? (
            <button
              type="button"
              className="header-menu-button"
              aria-label="Open sidebar"
              onClick={onMenuToggle}
            >
              <Menu01 size={20} />
            </button>
          ) : null}

          <div className="header-brand">
            <img src={logoPiagam} alt="Logo Piagam" className="header-brand-logo" />
          </div>
        </div>

        <div className="header-right">
          <span className="header-brand-title">Prodflow</span>
        </div>
      </div>

      {showBreadcrumbBar ? (
        <div className="header-breadcrumb">
          <div className="header-breadcrumb-content">
            <nav
              className="breadcrumb-nav"
              aria-label={departmentFilterProps ? 'Filter divisi' : 'Breadcrumb'}
              ref={breadcrumbFilterRef}
            >
              {renderBreadcrumb()}
            </nav>

            {hasSearch || hasNotification || onRefresh || hasToolbarActions ? (
              <div className="header-toolbar">
                {hasToolbarActions
                  ? toolbarActions.map((toolbarAction) => (
                      <button
                        key={toolbarAction.id}
                        type="button"
                        className="header-icon-button header-icon-button--compact"
                        aria-label={toolbarAction.ariaLabel}
                        title={toolbarAction.title ?? toolbarAction.ariaLabel}
                        onClick={toolbarAction.onClick}
                      >
                        {toolbarAction.icon}
                      </button>
                    ))
                  : null}

                {hasSearch ? (
                  <label
                    className="header-search header-search--compact"
                    aria-label={searchProps.ariaLabel ?? 'Search'}
                  >
                    <SearchMd size={16} className="header-search__icon header-search__icon--compact" />
                    <input
                      type="search"
                      className="header-search__input header-search__input--compact"
                      value={searchProps.value ?? ''}
                      placeholder={searchProps.placeholder ?? 'Search...'}
                      onChange={searchProps.onChange}
                      aria-label={searchProps.ariaLabel ?? 'Search'}
                      autoComplete="off"
                    />
                  </label>
                ) : null}

                {hasNotification ? (
                  <button
                    type="button"
                    className="header-icon-button header-icon-button--compact"
                    aria-label={notificationProps.ariaLabel ?? 'Open notifications'}
                    title={notificationProps.ariaLabel ?? 'Open notifications'}
                    onClick={() => setIsNotificationModalOpen(true)}
                  >
                    <Bell04 size={16} />
                  </button>
                ) : null}

                {onRefresh ? (
                  <button
                    type="button"
                    className="header-icon-button header-icon-button--compact"
                    aria-label="Refresh dashboard"
                    title="Refresh dashboard"
                    onClick={onRefresh}
                  >
                    <RefreshCw05 size={16} />
                  </button>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      {hasNotification && isNotificationModalOpen ? (
        <div
          className="header-modal-overlay"
          role="presentation"
          onClick={() => setIsNotificationModalOpen(false)}
        >
          <div
            className="header-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="header-notification-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="header-modal__header">
              <h2 className="header-modal__title" id="header-notification-title">
                {notificationProps.modalTitle ?? 'Notifications'}
              </h2>

              <button
                type="button"
                className="header-modal__close"
                aria-label="Close notification modal"
                onClick={() => setIsNotificationModalOpen(false)}
              >
                <XClose size={18} />
              </button>
            </div>

            <div className="header-modal__body">
              <div className="header-modal__empty" />
            </div>
          </div>
        </div>
      ) : null}

      {departmentDropdownPortal}
    </header>
  )
}

export default Header
