import React from 'react';
import { useTraffic } from '../context/TrafficContext';
import IntersectionMap from '../components/widgets/IntersectionMap';
import Card from '../components/ui/Card';
import Badge from '../components/ui/Badge';
import { Info, TrafficCone } from 'lucide-react';

export default function MapPage() {
  const { intersections } = useTraffic();

  const getSignalColorClass = (signal: string) => {
    switch (signal?.toUpperCase()) {
      case 'GREEN': return 'text-green-500 font-bold';
      case 'YELLOW': return 'text-yellow-500 font-bold';
      case 'RED': return 'text-red-500 font-bold';
      default: return 'text-slate-500';
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Intersection Map Widget takes 2/3 width */}
      <div className="lg:col-span-2">
        <IntersectionMap />
      </div>

      {/* Side Panel for Intersection Details takes 1/3 width */}
      <div className="space-y-6">
        <Card
          title="Intersection Directory"
          subtitle="Monitored junctions status details"
          icon={<TrafficCone className="h-5 w-5 text-purple-500" />}
        >
          <div className="space-y-4 mt-2">
            {intersections.map((intersection) => (
              <div 
                key={intersection.id}
                className="p-4 rounded-lg bg-slate-900/50 border border-slate-800 space-y-2 hover:border-slate-700 transition-colors"
              >
                <div className="flex items-center justify-between">
                  <h3 className="font-bold text-slate-100">{intersection.name}</h3>
                  <Badge 
                    label={intersection.congestion_status} 
                    variant={intersection.congestion_status === 'CONGESTED' ? 'danger' : 'success'} 
                    size="sm"
                  />
                </div>
                
                <div className="border-t border-slate-800/80 my-2" />
                
                <div className="grid grid-cols-2 gap-2 text-xs text-slate-400">
                  <div>
                    Signal state: <span className={getSignalColorClass(intersection.signal)}>{intersection.signal}</span>
                  </div>
                  <div>
                    Vehicles: <span className="font-semibold text-slate-200">{intersection.vehicle_count}</span>
                  </div>
                  <div className="col-span-2">
                    Density: <span className="font-semibold text-slate-200">{intersection.density} veh/km</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Card>
        
        <Card
          title="Junction Control Information"
          icon={<Info className="h-5 w-5 text-blue-500" />}
        >
          <div className="text-xs text-slate-400 space-y-2 leading-relaxed">
            <p>
              IntelliRoads employs a rule-based adaptive controller that modifies signal timing according to local lane densities.
            </p>
            <p className="font-semibold text-slate-300">
              Control Rules:
            </p>
            <ul className="list-disc pl-4 space-y-1">
              <li>Low Density (&lt;20 veh/km): <span className="text-green-400">20s green phase</span></li>
              <li>Medium Density (20-40 veh/km): <span className="text-yellow-400">35s green phase</span></li>
              <li>High Density (&gt;40 veh/km): <span className="text-red-400">55s green phase</span></li>
            </ul>
          </div>
        </Card>
      </div>
    </div>
  );
}
