import React from 'react';
export const state = (globalThis.__triviaEnv = globalThis.__triviaEnv || { user: null, calls: [] });
export function useAuth() { return { user: state.user, logout() {} }; }
const resp = (data) => Promise.resolve({ data });
const api = {
  listLocations: (game) => { state.calls.push('listLocations'); (globalThis.__locGames = globalThis.__locGames || []).push(game || ''); if (game && globalThis.__locationsByGame) return resp(globalThis.__locationsByGame[game] || []); if (!game && globalThis.__allLocations) return resp(globalThis.__allLocations); return resp(globalThis.__locations || [{ id: 'l1', slug: 'pub-one', name: 'Pub One', branding_images: [], overlay_images: [], admin_user_ids: [], games: ['trivia'] }]); },
  uploadLocationSponsor: (id, file) => { (globalThis.__sponsorCalls = globalThis.__sponsorCalls || []).push(['upload', id, file && file.name]); return resp({ id: 'sp-new', filename: file && file.name }); },
  deleteLocationSponsor: (id) => { (globalThis.__sponsorCalls = globalThis.__sponsorCalls || []).push(['delete', id]); return resp({}); },
  locationSponsorRawUrl: (id, imageId) => 'http://x/api/native/locations/' + id + '/sponsor/raw?v=' + (imageId || ''),
  getUsers: () => { state.calls.push('getUsers'); return resp([{ id: 'u1', name: 'Ann', role: 'admin' }]); },
  getEvents: () => resp([]),
};
export default api;
export const Panel = ({ scope }) => React.createElement("div", { "data-testid": "panel-" + scope }, "panel");
export { Panel as default_panel };
export const Header = () => React.createElement('div', { 'data-testid': 'app-header' });
export const FileButtons = () => React.createElement('div', null);
