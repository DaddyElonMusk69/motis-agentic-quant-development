import type { ReactNode } from "react";

type Column<T> = {
  key: string;
  header: string;
  align?: "left" | "right" | "center";
  render: (row: T) => ReactNode;
};

type DataTableProps<T> = {
  columns: Column<T>[];
  rows: T[];
  getRowKey: (row: T) => string;
  getRowClassName?: (row: T) => string | undefined;
  onRowClick?: (row: T) => void;
};

export function DataTable<T>({ columns, rows, getRowClassName, getRowKey, onRowClick }: DataTableProps<T>) {
  return (
    <div className="table-frame">
      <table className="data-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th className={column.align ? `is-${column.align}` : undefined} key={column.key}>
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td className="table-empty" colSpan={columns.length}>
                No rows available.
              </td>
            </tr>
          ) : (
            rows.map((row) => (
              <tr className={getRowClassName?.(row)} key={getRowKey(row)} onClick={onRowClick ? () => onRowClick(row) : undefined}>
                {columns.map((column) => (
                  <td className={column.align ? `is-${column.align}` : undefined} key={column.key}>
                    {column.render(row)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
