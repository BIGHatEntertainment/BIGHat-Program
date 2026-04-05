import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import StoryGenerator from '../../components/story/StoryGenerator';

export default function StoryGeneratorPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const userName = user?.name?.split(' ')[0]?.toLowerCase() || '';

  return (
    <StoryGenerator
      open={true}
      onClose={() => navigate('/')}
      userName={userName}
    />
  );
}
