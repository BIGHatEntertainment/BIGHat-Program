import React from 'react';
const strip = ({initial, animate, exit, transition, whileHover, whileTap, layout, ...rest}) => rest;
const make = (tag) => React.forwardRef((props, ref) => React.createElement(tag, {...strip(props), ref}, props.children));
export const motion = new Proxy({}, { get: (_, tag) => make(tag) });
export const AnimatePresence = ({children}) => <>{children}</>;
