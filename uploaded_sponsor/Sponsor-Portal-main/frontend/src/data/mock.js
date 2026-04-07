// BIG Hat Trivia - Sponsor Portal Mock Data

export const sponsorshipPackages = [
  {
    id: 'alacarte',
    name: 'À La Carte Options',
    description: 'Pick and choose individual promotional items - no package required!',
    standalone: true,
    items: [
      { id: 'alacarte-digital-mention', name: 'Digital Mentions', price: 100, description: 'Digital mention displayed during show' },
      { id: 'alacarte-round-overlay', name: 'Round Overlay', price: 100, description: 'Logo placement in one round overlay' },
      { id: 'alacarte-answer-overlay', name: 'Answer Overlay', price: 150, description: 'Logo placement in answer reveal' },
      { 
        id: 'alacarte-venue-sponsor', 
        name: 'Venue Sponsor', 
        price: 150, 
        description: 'Venue sponsorship for one location',
        hasCapacityPricing: true,
        capacityPricing: [
          { tier: '< 50', price: 150, stripeId: 'alacarte-venue-sponsor-small' },
          { tier: '> 50', price: 300, stripeId: 'alacarte-venue-sponsor-large' }
        ]
      },
      { 
        id: 'alacarte-round-sponsor', 
        name: 'Round Sponsor', 
        price: 100, 
        description: 'Sponsor a round for 30 days',
        duration: '30 days',
        hasCapacityPricing: true,
        capacityPricing: [
          { tier: '< 50', price: 100, stripeId: 'alacarte-round-sponsor-small' },
          { tier: '> 50', price: 200, stripeId: 'alacarte-round-sponsor-large' }
        ]
      },
      { id: 'alacarte-prize-sponsor', name: 'Prize Sponsor', price: 200, description: 'Sponsor prizes for events' }
    ],
    note: '25% discount for AZ local sponsors',
    featured: false
  },
  {
    id: 'bronze',
    name: 'Bronze Sponsor',
    price: 375,
    priceLabel: 'Starting at $375',
    description: 'Perfect for local businesses getting started',
    hasLocationOptions: true,
    locationOptions: [
      { id: 'bronze-single', name: 'Single Location', price: 375 },
      { id: 'bronze-all', name: 'All Locations', price: 500 }
    ],
    features: [
      { text: 'Small logo and name in sponsor section', icon: 'image' },
      { text: 'Spot on the thank you credit', icon: 'award' },
      { text: 'One host mention', icon: 'mic' }
    ],
    featured: false
  },
  {
    id: 'silver',
    name: 'Silver Sponsor',
    price: 850,
    priceLabel: '$850',
    description: 'Enhanced visibility with social reach',
    features: [
      { text: 'Big logo and name in sponsor section', icon: 'image' },
      { text: 'One social media promo per month', icon: 'share' },
      { text: 'One specific round hosted per month', icon: 'trophy' }
    ],
    featured: false
  },
  {
    id: 'gold',
    name: 'Gold Sponsor',
    price: 1800,
    priceLabel: '$1,800',
    description: 'Premium exposure across all events',
    features: [
      { text: 'One pre-show mention each event', icon: 'megaphone' },
      { text: 'One logo placement in a round overlay', icon: 'layers' },
      { text: 'Product/service description during sponsor display', icon: 'file-text' },
      { text: 'Mention at every bingo and karaoke event', icon: 'music' },
      { text: 'Link/QR code for metrics tracking', icon: 'link' },
      { text: 'Access to 16:9 wide format uploads', icon: 'monitor' }
    ],
    spotsAvailable: 4,
    featured: true
  },
  {
    id: 'star-tier',
    name: 'Star Tier Presenter',
    price: 4000,
    priceLabel: '$4,000',
    description: 'Maximum brand integration & exclusivity',
    features: [
      { text: 'Presented-by title before every trivia event', icon: 'star' },
      { text: 'Pre-show promotional spot', icon: 'play' },
      { text: 'Full page sponsor section (up to 30s graphic)', icon: 'maximize' },
      { text: 'Host can hand out flyers or materials', icon: 'gift' },
      { text: 'Custom social tags', icon: 'hash' },
      { text: 'Shown at every community event', icon: 'users' },
      { text: 'Automatic entry as sponsor of the BIG Trivia tournament', icon: 'trophy' },
      { text: 'Access to 16:9 wide format uploads', icon: 'monitor' }
    ],
    spotsAvailable: 2,
    featured: true
  }
];

export const mockUser = {
  id: 'user_123',
  email: 'sponsor@business.com',
  name: 'John Smith',
  picture: 'https://api.dicebear.com/7.x/initials/svg?seed=JS',
  businessName: 'Phoenix Coffee Co.',
  phone: '(602) 555-1234',
  website: 'https://phoenixcoffee.com',
  createdAt: '2025-01-15'
};

export const mockSponsorships = [
  {
    id: 'sp_001',
    packageId: 'gold',
    packageName: 'Gold Sponsor',
    status: 'active',
    startDate: '2025-06-01',
    endDate: '2026-06-01',
    price: 1800
  }
];

export const mockAssets = [
  {
    id: 'asset_001',
    name: 'Summer Promo Banner',
    type: 'image/gif',
    status: 'approved',
    uploadedAt: '2025-07-10',
    campaignName: 'Summer Special',
    startDate: '2025-07-15',
    endDate: '2025-08-31',
    thumbnail: 'https://placehold.co/400x225/1a1a2e/f4d03f?text=Summer+Promo'
  },
  {
    id: 'asset_002',
    name: 'Grand Opening Ad',
    type: 'image/png',
    status: 'pending',
    uploadedAt: '2025-08-01',
    campaignName: 'Grand Opening',
    startDate: '2025-08-15',
    endDate: '2025-09-15',
    thumbnail: 'https://placehold.co/400x225/1a1a2e/f4d03f?text=Grand+Opening'
  },
  {
    id: 'asset_003',
    name: 'Holiday Special',
    type: 'image/gif',
    status: 'revision_requested',
    uploadedAt: '2025-07-28',
    campaignName: 'Holiday 2025',
    startDate: '2025-11-01',
    endDate: '2025-12-31',
    notes: 'Please increase logo size and ensure text is readable at smaller sizes.',
    thumbnail: 'https://placehold.co/400x225/1a1a2e/f4d03f?text=Holiday+Special'
  }
];

export const mockShowPlacements = [
  { date: '2025-08-05', venue: 'Monkey Pants - Tempe', placement: 'Round 3 Overlay' },
  { date: '2025-08-06', venue: 'The Casual Pint - Gilbert', placement: 'Pre-show Mention' },
  { date: '2025-08-07', venue: 'Handlebar Pub - Mesa', placement: 'Answer Overlay' },
  { date: '2025-08-08', venue: 'The Casual Pint - Downtown', placement: 'Round 3 Overlay' }
];

export const mockStats = {
  totalShows: 48,
  estimatedImpressions: 3840,
  venuesCovered: 6,
  dateRange: 'June 1 - August 5, 2025'
};

export const faqs = [
  {
    question: 'What size should my GIF be?',
    answer: 'We recommend 1920x1080 pixels (16:9 aspect ratio) for best results. Maximum file size is 5MB. GIFs should loop seamlessly and be no longer than 10 seconds.'
  },
  {
    question: 'How often will my ad appear?',
    answer: 'This depends on your sponsorship tier. Gold sponsors appear at every event with pre-show mentions. Silver sponsors get monthly rotations. Bronze sponsors are included in the thank-you credits at all shows.'
  },
  {
    question: 'Can I update my creative?',
    answer: 'Yes! You can upload new creatives anytime through your dashboard. New assets go through our approval process (typically 24-48 hours) before going live.'
  },
  {
    question: 'What content is not allowed?',
    answer: 'We do not accept explicit content, offensive material, copyrighted media without permission, or content that violates local advertising laws.'
  },
  {
    question: 'How do I know my ad is being shown?',
    answer: 'Your dashboard shows upcoming placements and past show history. Gold and Star Tier sponsors also receive QR code tracking for detailed metrics.'
  },
  {
    question: 'Can I target specific venues?',
    answer: 'Yes! Venue-specific sponsorships are available as add-ons. Contact our team to discuss venue targeting options.'
  }
];

export const venues = [
  'Monkey Pants - Tempe',
  'The Casual Pint - Gilbert',
  'The Casual Pint - Downtown Phoenix',
  'Handlebar Pub - Mesa',
  'Four Peaks Brewing - Tempe',
  'SunUp Brewing - Phoenix'
];

// Locations for admin management
export const mockLocations = [
  {
    id: 'loc_001',
    name: 'Monkey Pants',
    address: '230 W 5th St, Tempe, AZ 85281',
    city: 'Tempe',
    dayOfWeek: 'Thursday',
    time: '8:00 PM',
    capacityTier: '> 50',
    status: 'active',
    contactName: 'Mike Johnson',
    contactPhone: '(480) 555-1234',
    notes: 'Popular college crowd venue'
  },
  {
    id: 'loc_002',
    name: 'The Casual Pint',
    address: '1245 S Gilbert Rd, Gilbert, AZ 85296',
    city: 'Gilbert',
    dayOfWeek: 'Tuesday',
    time: '7:00 PM',
    capacityTier: '> 50',
    status: 'active',
    contactName: 'Sarah Williams',
    contactPhone: '(480) 555-2345',
    notes: 'Family-friendly atmosphere'
  },
  {
    id: 'loc_003',
    name: 'The Casual Pint - Downtown',
    address: '123 N Central Ave, Phoenix, AZ 85004',
    city: 'Phoenix',
    dayOfWeek: 'Wednesday',
    time: '7:30 PM',
    capacityTier: '100+',
    status: 'active',
    contactName: 'Tom Davis',
    contactPhone: '(602) 555-3456',
    notes: 'Downtown business crowd'
  },
  {
    id: 'loc_004',
    name: 'Handlebar Pub',
    address: '456 W Main St, Mesa, AZ 85201',
    city: 'Mesa',
    dayOfWeek: 'Friday',
    time: '8:00 PM',
    capacityTier: '> 50',
    status: 'active',
    contactName: 'Lisa Brown',
    contactPhone: '(480) 555-4567',
    notes: 'Great outdoor patio space'
  },
  {
    id: 'loc_005',
    name: 'Four Peaks Brewing',
    address: '1340 E 8th St, Tempe, AZ 85281',
    city: 'Tempe',
    dayOfWeek: 'Monday',
    time: '7:00 PM',
    capacityTier: '< 50',
    status: 'inactive',
    contactName: 'Chris Taylor',
    contactPhone: '(480) 555-5678',
    notes: 'Currently on seasonal break'
  },
  {
    id: 'loc_006',
    name: 'SunUp Brewing',
    address: '322 E Camelback Rd, Phoenix, AZ 85012',
    city: 'Phoenix',
    dayOfWeek: 'Saturday',
    time: '6:00 PM',
    capacityTier: '> 50',
    status: 'active',
    contactName: 'Amanda Wilson',
    contactPhone: '(602) 555-6789',
    notes: 'Weekend evening crowd'
  }
];

export const mediaRequirements = {
  formats: ['GIF', 'PNG', 'JPG', 'JPEG'],
  maxFileSize: '5MB',
  aspectRatios: ['16:9 (recommended)', '1:1 (square)'],
  resolutions: {
    recommended: '1920x1080',
    minimum: '1280x720'
  },
  gifMaxDuration: '10 seconds'
};

// Admin mock data
export const mockPendingApprovals = [
  {
    id: 'asset_002',
    sponsorName: 'Phoenix Coffee Co.',
    sponsorEmail: 'sponsor@business.com',
    assetName: 'Grand Opening Ad',
    type: 'image/png',
    uploadedAt: '2025-08-01',
    campaignName: 'Grand Opening',
    startDate: '2025-08-15',
    endDate: '2025-09-15',
    thumbnail: 'https://placehold.co/400x225/1a1a2e/f4d03f?text=Grand+Opening',
    package: 'Gold Sponsor'
  },
  {
    id: 'asset_004',
    sponsorName: 'Desert Auto Repair',
    sponsorEmail: 'info@desertauto.com',
    assetName: 'Service Special',
    type: 'image/gif',
    uploadedAt: '2025-08-02',
    campaignName: 'August Service',
    startDate: '2025-08-10',
    endDate: '2025-08-31',
    thumbnail: 'https://placehold.co/400x225/1a1a2e/f4d03f?text=Auto+Service',
    package: 'Silver Sponsor'
  }
];

export const mockAllSponsors = [
  {
    id: 'user_123',
    businessName: 'Phoenix Coffee Co.',
    email: 'sponsor@business.com',
    package: 'Gold Sponsor',
    status: 'active',
    assetsCount: 3,
    joinedAt: '2025-01-15'
  },
  {
    id: 'user_124',
    businessName: 'Desert Auto Repair',
    email: 'info@desertauto.com',
    package: 'Silver Sponsor',
    status: 'active',
    assetsCount: 1,
    joinedAt: '2025-03-20'
  },
  {
    id: 'user_125',
    businessName: 'Mesa Fitness Center',
    email: 'contact@mesafitness.com',
    package: 'Bronze Sponsor',
    status: 'active',
    assetsCount: 2,
    joinedAt: '2025-05-10'
  }
];