import React from 'react';

const PERIODS = [
  { id: 1, label: 'Hour 1' },
  { id: 2, label: 'Hour 2' },
  { id: 3, label: 'Hour 3' },
  { id: 4, label: 'Hour 4' },
  { id: 'lunch', label: 'LUNCH', isLunch: true },
  { id: 5, label: 'Hour 5' },
  { id: 6, label: 'Hour 6' },
  { id: 7, label: 'Hour 7' },
];

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

export default function PeriodGrid({ scheduleItems = [] }) {
  const getSlotContent = (day, period) => {
    return scheduleItems.find(
      (item) =>
        item.day.toLowerCase() === day.toLowerCase() &&
        item.period_start <= period &&
        item.period_end >= period
    );
  };

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="w-full text-sm text-center border-collapse">
        <thead className="bg-slate-100 text-slate-700 font-semibold border-b">
          <tr>
            <th className="p-3 border-r">Day</th>
            {PERIODS.map((p) => (
              <th key={p.id} className={`p-3 border-r ${p.isLunch ? 'bg-amber-100 text-amber-900 font-bold' : ''}`}>
                {p.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {DAYS.map((day) => (
            <tr key={day} className="border-b hover:bg-slate-50">
              <td className="p-3 font-medium bg-slate-50 border-r text-slate-800">{day}</td>
              {PERIODS.map((p) => {
                if (p.isLunch) {
                  return <td key={p.id} className="bg-amber-50/50 border-r text-xs text-amber-700 font-medium">Break</td>;
                }
                const match = getSlotContent(day, p.id);
                return (
                  <td key={p.id} className={`p-2 border-r ${match ? 'bg-indigo-50 text-indigo-900 font-medium' : 'text-slate-400'}`}>
                    {match ? match.subject || 'Class' : '-'}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}