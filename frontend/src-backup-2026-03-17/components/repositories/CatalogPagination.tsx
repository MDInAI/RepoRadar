export function CatalogPagination({
  page,
  totalPages,
  pageSize,
  totalCount,
  onPageChange,
  onPageSizeChange,
}: {
  page: number;
  totalPages: number;
  pageSize: number;
  totalCount: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
}) {
  const canGoPrevious = page > 1;
  const canGoNext = totalPages > 0 && page < totalPages;

  return (
    <section className="flex flex-col gap-4 rounded-[2rem] border border-black/10 bg-white/85 px-5 py-4 shadow-[0_18px_60px_-40px_rgba(15,23,42,0.5)] backdrop-blur lg:flex-row lg:items-center lg:justify-between">
      <div>
        <p className="text-sm font-semibold text-slate-900">
          Page {totalPages === 0 ? 0 : page} of {totalPages}
        </p>
        <p className="mt-1 text-sm text-slate-600">{totalCount} total repositories</p>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <label className="flex items-center gap-3 text-sm font-medium text-slate-700">
          <span>Rows per page</span>
          <select
            aria-label="Rows per page"
            className="rounded-full border border-slate-300 bg-white px-4 py-2 text-sm text-slate-900"
            value={pageSize}
            onChange={(event) => onPageSizeChange(Number.parseInt(event.target.value, 10))}
          >
            {[30, 50, 100].map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>

        <div className="flex items-center gap-2">
          <button
            className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-800 transition hover:border-slate-400 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
            disabled={!canGoPrevious}
            type="button"
            onClick={() => onPageChange(page - 1)}
          >
            Previous
          </button>
          <button
            className="rounded-full border border-slate-950 bg-slate-950 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
            disabled={!canGoNext}
            type="button"
            onClick={() => onPageChange(page + 1)}
          >
            Next
          </button>
        </div>
      </div>
    </section>
  );
}
