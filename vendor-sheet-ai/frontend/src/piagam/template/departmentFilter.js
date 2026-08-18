export const ALL_DEPARTMENTS_FILTER_ID = 'all'
export const ALL_DEPARTMENTS_FILTER_LABEL = 'All Departments'

export function getDepartmentFilterOptions(departments = []) {
  return [
    { id: ALL_DEPARTMENTS_FILTER_ID, label: ALL_DEPARTMENTS_FILTER_LABEL },
    ...departments.map((department) => ({
      id: department.id ?? department.value ?? department.label,
      label: department.label ?? department.name ?? department.id,
    })),
  ]
}

export function getSelectedDepartmentFilterLabel(departments = [], selectedDepartmentId) {
  if (!selectedDepartmentId || selectedDepartmentId === ALL_DEPARTMENTS_FILTER_ID) {
    return ALL_DEPARTMENTS_FILTER_LABEL
  }

  const selectedDepartment = departments.find(
    (department) => String(department.id ?? department.value) === String(selectedDepartmentId),
  )

  return selectedDepartment?.label ?? selectedDepartment?.name ?? ALL_DEPARTMENTS_FILTER_LABEL
}
