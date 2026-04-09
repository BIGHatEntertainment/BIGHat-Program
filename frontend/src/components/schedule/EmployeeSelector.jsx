import React from 'react';
import { User } from 'lucide-react';
import { Label } from '../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';

const EmployeeSelector = ({ employees, selectedEmployee, onSelectEmployee }) => {
  return (
    <div className="space-y-3">
      <div className="flex items-center space-x-2">
        <User className="h-5 w-5 text-primary" />
        <Label htmlFor="employee" className="text-lg font-semibold">
          Select Your Name
        </Label>
      </div>
      <Select value={selectedEmployee || ''} onValueChange={onSelectEmployee}>
        <SelectTrigger id="employee" className="w-full sm:w-80 h-12 text-base border-2 hover:border-primary transition-smooth">
          <SelectValue placeholder="Choose your name to claim events" />
        </SelectTrigger>
        <SelectContent>
          {employees.map((employee) => (
            <SelectItem key={employee.id} value={employee.id} className="text-base cursor-pointer">
              {employee.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {!selectedEmployee && (
        <p className="text-sm text-gray-400">
          Please select your name to claim events
        </p>
      )}
    </div>
  );
};

export default EmployeeSelector;
