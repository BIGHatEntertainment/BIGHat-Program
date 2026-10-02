import React from 'react';
export const Button = ({children, onClick, disabled, ...p}) => <button onClick={onClick} disabled={disabled} data-testid={p['data-testid']}>{children}</button>;
export const Card = ({children}) => <div>{children}</div>;
export const CardContent = Card; export const CardHeader = Card; export const CardTitle = Card;
const Ctx = React.createContext(null);
export const RadioGroup = ({value, onValueChange, children}) => <Ctx.Provider value={{value, onValueChange}}><div role="radiogroup">{children}</div></Ctx.Provider>;
export const RadioGroupItem = ({value, id}) => { const c = React.useContext(Ctx); return <input type="radio" id={id} value={value} checked={c.value===value} onChange={()=>c.onValueChange(value)} />; };
export const Label = ({children, htmlFor, className}) => <label htmlFor={htmlFor} className={className}>{children}</label>;
export default () => null;
