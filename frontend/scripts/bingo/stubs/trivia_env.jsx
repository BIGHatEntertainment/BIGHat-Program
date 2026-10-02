import React from 'react';
export const state = (globalThis.__triviaEnv = globalThis.__triviaEnv || { user: null, calls: [] });
export function useAuth() { return { user: state.user, logout() {} }; }
const resp = (data) => Promise.resolve({ data });
const api = {
  listLocations: () => { state.calls.push('listLocations'); return resp([{ id: 'l1', slug: 'pub-one', name: 'Pub One', branding_images: [], overlay_images: [], admin_user_ids: [] }]); },
  getUsers: () => { state.calls.push('getUsers'); return resp([{ id: 'u1', name: 'Ann', role: 'admin' }]); },
  getEvents: () => resp([]),
};
export default api;
export const Panel = ({ scope }) => React.createElement("div", { "data-testid": "panel-" + scope }, "panel");
export { Panel as default_panel };
export const Header = () => React.createElement('div', { 'data-testid': 'app-header' });
export const FileButtons = () => React.createElement('div', null);
