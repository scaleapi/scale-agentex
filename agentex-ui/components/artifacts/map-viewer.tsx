'use client';

import { useState, useEffect, useCallback } from 'react';

import {
  APIProvider,
  Map,
  AdvancedMarker,
  useMap,
} from '@vis.gl/react-google-maps';
import { Loader2, AlertCircle, Truck } from 'lucide-react';
import { v4 as uuidv4 } from 'uuid';

import type { MapMetadata } from '@/lib/types';

type MapViewerProps = {
  address: string;
  metadata?: MapMetadata | null | undefined;
};

function MapContent({ address, metadata }: MapViewerProps) {
  const map = useMap();
  const [location, setLocation] = useState<{ lat: number; lng: number } | null>(
    null
  );
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const geocodeAddress = useCallback(
    async (address: string) => {
      try {
        setIsLoading(true);
        setError(null);

        const geocoder = new google.maps.Geocoder();
        const result = await geocoder.geocode({ address });

        if (result.results && result.results.length > 0) {
          const location = result.results[0]?.geometry.location;
          if (location) {
            const coords = {
              lat: location.lat(),
              lng: location.lng(),
            };
            setLocation(coords);

            if (map) {
              map.setCenter(coords);
              map.setZoom(12);
            }
          } else {
            setError('Could not determine location coordinates');
          }
        } else {
          setError(`No results found for address: ${address}`);
        }
      } catch (err) {
        setError(
          err instanceof Error ? err.message : 'Failed to geocode address'
        );
      } finally {
        setIsLoading(false);
      }
    },
    [map]
  );

  useEffect(() => {
    if (address) {
      geocodeAddress(address);
    }
  }, [address, geocodeAddress]);

  if (isLoading) {
    return (
      <div className="bg-background absolute inset-0 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="text-muted-foreground h-8 w-8 animate-spin" />
          <p className="text-muted-foreground text-sm">
            Loading map location...
          </p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-background absolute inset-0 flex items-center justify-center p-8">
        <div className="max-w-md space-y-4 text-center">
          <AlertCircle className="text-destructive mx-auto h-12 w-12" />
          <div className="space-y-2">
            <h3 className="text-lg font-semibold">Failed to Load Location</h3>
            <p className="text-muted-foreground text-sm">{error}</p>
          </div>
          <div className="border-border mt-4 border-t pt-4">
            <p className="text-muted-foreground text-xs">Address: {address}</p>
          </div>
        </div>
      </div>
    );
  }

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return null;
    try {
      const date = new Date(dateStr);
      return date.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
      });
    } catch {
      return dateStr;
    }
  };

  // Determine if this is a departed shipment
  const isDeparted = metadata?.eventType === 'Shipment_Departed_Factory';

  // Choose colors based on event type
  const borderColor = isDeparted ? 'border-blue-500' : 'border-green-500';
  const bgColor = isDeparted
    ? 'bg-blue-100 dark:bg-blue-900/30'
    : 'bg-green-100 dark:bg-green-900/30';
  const iconColor = isDeparted
    ? 'text-blue-600 dark:text-blue-400'
    : 'text-green-600 dark:text-green-400';
  const textColor = isDeparted
    ? 'text-blue-600 dark:text-blue-400'
    : 'text-green-600 dark:text-green-400';
  const arrowColor = isDeparted ? 'border-t-blue-500' : 'border-t-green-500';

  return (
    <>
      {location && (
        <AdvancedMarker position={location}>
          <div className="flex flex-col items-center">
            <div
              className={`min-w-[200px] rounded-lg border-2 ${borderColor} bg-white px-4 py-3 shadow-lg dark:bg-gray-800`}
            >
              <div className="flex items-center gap-3">
                <div className={`flex-shrink-0 rounded-full ${bgColor} p-2`}>
                  <Truck className={`h-5 w-5 ${iconColor}`} />
                </div>

                <div className="min-w-0 flex-1">
                  {metadata?.item && (
                    <p className="truncate text-sm font-semibold text-gray-900 dark:text-gray-100">
                      {metadata.item}
                    </p>
                  )}

                  {isDeparted ? (
                    <div className="mt-0.5 space-y-0.5">
                      {metadata?.dateDeparted && (
                        <p className="text-xs font-medium text-gray-900 dark:text-gray-100">
                          Departed:{' '}
                          <span className={textColor}>
                            {formatDate(metadata.dateDeparted)}
                          </span>
                        </p>
                      )}
                      {metadata?.eta && (
                        <p className="text-xs font-medium text-gray-900 dark:text-gray-100">
                          ETA:{' '}
                          <span className={textColor}>
                            {formatDate(metadata.eta)}
                          </span>
                        </p>
                      )}
                    </div>
                  ) : (
                    <>
                      {metadata?.deliveryDate && (
                        <p className="mt-0.5 text-xs font-medium text-gray-900 dark:text-gray-100">
                          Arrived:{' '}
                          <span className={textColor}>
                            {formatDate(metadata.deliveryDate)}
                          </span>
                        </p>
                      )}
                    </>
                  )}

                  {!metadata?.item &&
                    !metadata?.deliveryDate &&
                    !metadata?.dateDeparted &&
                    !metadata?.eta && (
                      <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
                        Delivery Location
                      </p>
                    )}
                </div>
              </div>
            </div>

            <div
              className={`h-0 w-0 ${arrowColor} border-t-[12px] border-r-[10px] border-l-[10px] border-r-transparent border-l-transparent`}
            />
          </div>
        </AdvancedMarker>
      )}
    </>
  );
}

export function MapViewer({ address, metadata }: MapViewerProps) {
  const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;

  if (!apiKey) {
    return (
      <div className="bg-background flex h-full items-center justify-center p-8">
        <div className="max-w-md space-y-4 text-center">
          <AlertCircle className="text-destructive mx-auto h-12 w-12" />
          <div className="space-y-2">
            <h3 className="text-lg font-semibold">Maps API Key Missing</h3>
            <p className="text-muted-foreground text-sm">
              Please set NEXT_PUBLIC_GOOGLE_MAPS_API_KEY in your environment
              variables.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full w-full">
      <APIProvider
        apiKey={apiKey}
        solutionChannel="gmp_mcp_codeassist_v0.1_github"
      >
        <Map
          mapId={uuidv4()}
          className="h-full w-full"
          gestureHandling="greedy"
        >
          <MapContent address={address} metadata={metadata} />
        </Map>
      </APIProvider>
    </div>
  );
}
