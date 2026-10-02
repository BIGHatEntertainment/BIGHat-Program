import React from 'react';
export default function Panel({ scope }) { return React.createElement('div', { 'data-testid': 'panel-' + (scope || 'x') }, 'panel'); }
