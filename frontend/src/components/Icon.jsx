const paths = {
  home: 'm3 10 9-7 9 7v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z M9 21v-7h6v7',
  compass: 'M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z M16 8l-2 6-6 2 2-6z',
  fridge: 'M7 3h10a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z M5 10h14 M8 6v1 M8 13v3',
  trend: 'm3 17 6-6 4 4 7-8 M15 7h5v5',
  chart: 'M4 3v17h17 M9 16v-4 M14 16V8 M19 16V5',
  search: 'M16 10a6 6 0 1 1-12 0 6 6 0 0 1 12 0Z M15 15l5 5',
  user: 'M16 8a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z M4 21v-2a5 5 0 0 1 5-5h6a5 5 0 0 1 5 5v2',
  brand: 'M4 11h16a8 8 0 0 1-16 0Z M8 21h8 M9 7c-2-2 2-2 0-4 M15 7c-2-2 2-2 0-4',
  market: 'M4 10h16l-2 10H6L4 10Z M8 10l4-6 4 6 M9 14v2 M15 14v2',
  logout: 'M10 4H5v16h5 M9 12h12 m-4-4 4 4-4 4',
}

export default function Icon({ name, size = 22 }) {
  return <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d={paths[name]} /></svg>
}
