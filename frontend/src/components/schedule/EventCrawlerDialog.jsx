import React, { useState } from 'react';
import axios from 'axios';
import { Calendar, MapPin, Clock, RefreshCw, AlertCircle } from 'lucide-react';
import { Button } from '../ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog';
import { Card, CardContent } from '../ui/card';
import { Badge } from '../ui/badge';
import { toast } from 'sonner';
import { format, parseISO } from 'date-fns';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const EventCrawlerDialog = ({ open, onOpenChange }) => {
  const [loading, setLoading] = useState(false);
  const [crawledEvents, setCrawledEvents] = useState([]);
  const [venuesCrawled, setVenuesCrawled] = useState([]);
  const [crawledAt, setCrawledAt] = useState(null);
  const [errors, setErrors] = useState([]);

  const handleCrawl = async () => {
    setLoading(true);
    try {
      const response = await axios.get(`${API}/events/crawler/phoenix`);
      
      setCrawledEvents(response.data.events);
      setVenuesCrawled(response.data.venues_crawled);
      setCrawledAt(response.data.crawled_at);
      setErrors(response.data.errors || []);
      
      toast.success(`Found ${response.data.total_events} events from Phoenix venues!`);
    } catch (error) {
      console.error('Error crawling events:', error);
      toast.error('Failed to crawl events');
    } finally {
      setLoading(false);
    }
  };

  const getEventTypeColor = (eventType) => {
    const colors = {
      'baseball': 'bg-green-100 text-green-800 border-green-300',
      'basketball': 'bg-orange-100 text-orange-800 border-orange-300',
      'concert': 'bg-purple-100 text-purple-800 border-purple-300',
      'other': 'bg-blue-100 text-blue-800 border-blue-300'
    };
    return colors[eventType] || colors.other;
  };

  const groupEventsByDate = () => {
    const grouped = {};
    crawledEvents.forEach(event => {
      if (!grouped[event.date]) {
        grouped[event.date] = [];
      }
      grouped[event.date].push(event);
    });
    return grouped;
  };

  const groupedEvents = groupEventsByDate();
  const sortedDates = Object.keys(groupedEvents).sort();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent style={{ backgroundColor: "#0d1220", border: "1px solid rgba(251, 221, 104, 0.2)" }} className="max-w-5xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-2xl flex items-center space-x-2">
            <Calendar className="h-6 w-6 text-primary" />
            <span>Phoenix Event Crawler</span>
          </DialogTitle>
          <DialogDescription>
            Check for concerts, sports games, and major events in Phoenix that might affect scheduling
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Crawl Button */}
          {!loading && crawledEvents.length === 0 && (
            <div className="text-center py-8">
              <Button
                onClick={handleCrawl}
                className="bg-blue-500 hover:bg-blue-600 text-white"
                size="lg"
              >
                <RefreshCw className="h-5 w-5 mr-2" />
                Crawl Phoenix Events
              </Button>
              <p className="text-sm text-muted-foreground mt-4">
                Searches Chase Field, Footprint Center, and Phoenix Convention Center
              </p>
            </div>
          )}

          {/* Loading State */}
          {loading && (
            <div className="text-center py-12">
              <div className="animate-spin rounded-full h-12 w-12 border-b-4 border-primary mx-auto mb-4"></div>
              <p className="text-lg font-semibold">Crawling Phoenix venues...</p>
              <p className="text-sm text-muted-foreground">This may take a few moments</p>
            </div>
          )}

          {/* Results */}
          {!loading && crawledEvents.length > 0 && (
            <>
              {/* Summary */}
              <Card className="bg-blue-50 border-2 border-blue-300">
                <CardContent className="pt-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm text-muted-foreground">Found Events</p>
                      <p className="text-3xl font-bold text-blue-700">{crawledEvents.length}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-sm text-muted-foreground">Venues Searched</p>
                      <p className="text-lg font-semibold">{venuesCrawled.join(', ')}</p>
                    </div>
                    <Button
                      onClick={handleCrawl}
                      variant="outline"
                      size="sm"
                    >
                      <RefreshCw className="h-4 w-4 mr-2" />
                      Refresh
                    </Button>
                  </div>
                  {crawledAt && (
                    <p className="text-xs text-muted-foreground mt-2">
                      Last updated: {(() => {
                        try {
                          return format(parseISO(crawledAt), 'MMM d, yyyy h:mm a');
                        } catch {
                          return new Date(crawledAt).toLocaleString();
                        }
                      })()}
                    </p>
                  )}
                </CardContent>
              </Card>

              {/* Errors */}
              {errors.length > 0 && (
                <Card className="bg-yellow-50 border-2 border-yellow-300">
                  <CardContent className="pt-6">
                    <div className="flex items-start space-x-2">
                      <AlertCircle className="h-5 w-5 text-yellow-600 flex-shrink-0 mt-0.5" />
                      <div>
                        <p className="font-semibold text-yellow-900">Some venues couldn&apos;t be crawled:</p>
                        <ul className="text-sm text-yellow-800 mt-1">
                          {errors.map((error, idx) => (
                            <li key={idx}>• {error}</li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Event List */}
              <div className="space-y-4">
                <h3 className="text-lg font-semibold">Upcoming Events by Date</h3>
                {sortedDates.map(date => (
                  <Card key={date} className="border-2">
                    <CardContent className="pt-6">
                      <h4 className="font-bold text-lg mb-3 flex items-center space-x-2">
                        <Calendar className="h-5 w-5 text-primary" />
                        <span>{(() => {
                          try {
                            return format(parseISO(date), 'EEEE, MMMM d, yyyy');
                          } catch {
                            return date;
                          }
                        })()}</span>
                      </h4>
                      <div className="space-y-2">
                        {groupedEvents[date].map((event) => (
                          <div
                            key={event.id}
                            className="p-3 bg-muted rounded-lg flex items-start justify-between"
                          >
                            <div className="flex-1">
                              <div className="flex items-center space-x-2 mb-1">
                                <span className="text-2xl">{event.icon}</span>
                                <h5 className="font-semibold">{event.name}</h5>
                              </div>
                              <div className="flex items-center space-x-4 text-sm text-muted-foreground">
                                <div className="flex items-center space-x-1">
                                  <MapPin className="h-3 w-3" />
                                  <span>{event.venue}</span>
                                </div>
                                <div className="flex items-center space-x-1">
                                  <Clock className="h-3 w-3" />
                                  <span>{event.time}</span>
                                </div>
                              </div>
                            </div>
                            <Badge className={`${getEventTypeColor(event.event_type)} border`}>
                              {event.event_type}
                            </Badge>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>

              {/* Info Box */}
              <Card className="bg-green-50 border-2 border-green-300">
                <CardContent className="pt-6">
                  <p className="text-sm font-semibold text-green-900 mb-2">💡 How to use this info:</p>
                  <ul className="text-sm text-green-800 space-y-1">
                    <li>• Check for busy sporting events or concerts near your venues</li>
                    <li>• Avoid scheduling trivia/karaoke on dates with heavy traffic</li>
                    <li>• Plan ahead for major events that might affect parking or attendance</li>
                  </ul>
                </CardContent>
              </Card>

              {/* Configuration Notice */}
              {crawledEvents.some(e => e.source === 'Configuration Required') && (
                <Card className="bg-amber-50 border-2 border-amber-400">
                  <CardContent className="pt-6">
                    <p className="text-sm font-semibold text-amber-900 mb-2">⚙️ To Get Real Event Data:</p>
                    <div className="text-sm text-amber-800 space-y-2">
                      <p>Configure a Ticketmaster API key to fetch actual events:</p>
                      <ol className="list-decimal list-inside space-y-1 ml-2">
                        <li>Get a free API key from <a href="https://developer.ticketmaster.com/" target="_blank" rel="noopener noreferrer" className="underline font-semibold">developer.ticketmaster.com</a></li>
                        <li>Add to backend .env file: <code className="bg-amber-200 px-2 py-0.5 rounded">TICKETMASTER_API_KEY=your_key_here</code></li>
                        <li>Restart backend and refresh this crawler</li>
                      </ol>
                      <p className="text-xs mt-2">This will show real concerts, sports games, and events from Footprint Center, Chase Field, and more!</p>
                    </div>
                  </CardContent>
                </Card>
              )}
            </>
          )}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
          >
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default EventCrawlerDialog;
