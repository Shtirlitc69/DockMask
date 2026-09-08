import { useMemo } from 'react';
import { RepBadge } from './RepBadge';
import type { DocElement, DocSegment, DocTableCell, DocTable, DocLine, Replacement } from '../types';

export function DocumentPreview({ document, replacements }: { document: DocElement[]; replacements: Replacement[] }) {
  const repMap = useMemo(() => {
    const m: Record<string, Replacement> = {};
    replacements.forEach(r => { m[r.id] = r; });
    return m;
  }, [replacements]);

  function renderSegments(segments: DocSegment[]) {
    return segments.map((seg, i) => {
      if (seg.replacementId && repMap[seg.replacementId]) {
        return <RepBadge key={i} rep={repMap[seg.replacementId]} />;
      }
      return <span key={i}>{seg.text}</span>;
    });
  }

  function renderCell(cell: DocTableCell, key: string | number) {
    const align = cell.align === 'right' ? 'text-right' : cell.align === 'center' ? 'text-center' : 'text-left';
    return (
      <td
        key={key}
        className={`py-1.5 px-2.5 text-[12px] border-b ${align}`}
        style={{
          borderColor: '#d1d5db',
          fontWeight: cell.header ? 600 : 400,
          background: cell.header ? '#f3f4f6' : 'transparent',
          color: '#111827',
        }}
      >
        {renderSegments(cell.segments)}
      </td>
    );
  }

  return (
    <div
      className="rounded-lg shadow-xl overflow-auto text-[13px] leading-relaxed"
      style={{ background: '#fff', color: '#111827', fontFamily: "'Outfit', sans-serif", minHeight: 400 }}
    >
      <div className="p-8 space-y-1.5">
        {document.map(elem => {
          if (elem.type === 'table') {
            const tbl = elem as DocTable;
            return (
              <div key={tbl.id} className="overflow-x-auto my-3">
                <table className="w-full border-collapse border rounded text-xs" style={{ borderColor: '#d1d5db' }}>
                  <tbody>
                    {tbl.rows.map((row, ri) => (
                      <tr key={ri}>
                        {row.map((c, ci) => renderCell(c, ci))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          }

          const line = elem as DocLine;
          if (line.type === 'divider') {
            return <hr key={line.id} style={{ borderColor: '#e5e7eb', marginTop: 6, marginBottom: 6 }} />;
          }
          if (line.type === 'spacer') {
            return <div key={line.id} className="h-2" />;
          }

          const cn = [
            line.type === 'title' ? 'text-base font-bold tracking-wide' : '',
            line.type === 'subtitle' ? 'text-sm text-gray-500' : '',
            line.type === 'label' ? 'text-[11px] font-semibold tracking-widest uppercase mt-1 text-gray-500' : '',
            line.type === 'field' ? 'text-[13px]' : '',
            line.type === 'text' ? 'text-xs text-gray-400 italic' : '',
            line.bold ? 'font-semibold' : '',
            line.centered ? 'text-center' : '',
          ].filter(Boolean).join(' ');

          return (
            <div
              key={line.id}
              className={cn}
              style={line.indent ? { paddingLeft: `${line.indent * 16}px` } : {}}
            >
              {renderSegments(line.segments)}
            </div>
          );
        })}
      </div>
    </div>
  );
}