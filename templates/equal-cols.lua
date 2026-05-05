-- Pandoc Lua filter: force all table columns to equal width (1fr each)
-- Without this, pandoc calculates column widths from markdown separator
-- lengths (number of dashes), which produces lopsided tables when
-- headers have uneven character counts.
function Table(tbl)
  local ncols = #tbl.colspecs
  local new_colspecs = {}
  for i = 1, ncols do
    -- Keep alignment, set width to nil (auto/equal)
    new_colspecs[i] = {tbl.colspecs[i][1], nil}
  end
  tbl.colspecs = new_colspecs
  return tbl
end
