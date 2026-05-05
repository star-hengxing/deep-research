-- Convert horizontal rules (--- in markdown) to page breaks in PDF output
-- Runs after the markdown is parsed, before Typst writing
function HorizontalRule()
  return pandoc.RawBlock('typst', '#pagebreak()')
end
