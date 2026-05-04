import React, { createContext, useContext, useState, useEffect } from 'react';
import axios from 'axios';

const SubscriptionContext = createContext();

export const SubscriptionProvider = ({ children }) => {
  const [subscription, setSubscription] = useState({
    all_enabled: true,
    modules: {
      trivia: true,
      bingo: true,
      scoreboard: true,
      roundmaker: true,
      story: true,
      scheduler: true
    }
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const response = await axios.get('/api/subscription/status');
        setSubscription(response.data);
      } catch (error) {
        console.error('Failed to fetch subscription status', error);
      } finally {
        setLoading(false);
      }
    };
    fetchStatus();
  }, []);

  const isModuleEnabled = (moduleId) => {
    return subscription.all_enabled || (subscription.modules && subscription.modules[moduleId]);
  };

  return (
    <SubscriptionContext.Provider value={{ subscription, loading, isModuleEnabled }}>
      {children}
    </SubscriptionContext.Provider>
  );
};

export const useSubscription = () => {
  const context = useContext(SubscriptionContext);
  if (!context) {
    throw new Error('useSubscription must be used within a SubscriptionProvider');
  }
  return context;
};
