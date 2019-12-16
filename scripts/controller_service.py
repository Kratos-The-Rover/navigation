#!/usr/bin/env python
from navigation.srv import Planner,PlannerResponse
import numpy as np
import sys
import os
import rospy
from std_msgs.msg import String
from sensor_msgs.msg import LaserScan
from navigation.msg import *
# from context import RRT, utils
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../rrt_for_scan')))

from utils_scan import scan_obstacle_checker, make_obstacles_scan, check_intersection_scan
from utils_scan import adjustable_random_sampler as sampler
from descartes import PolygonPatch
from shapely.geometry import Polygon, Point, LineString
import random
import math, time
import matplotlib.pyplot as plt

sys.path.append(os.path.dirname(os.path.abspath(__file__)) +
                "/../rrt_for_scan/")


try:
    from rrt import RRT
except ImportError:
    raise

def find_near_nodes(node_list, new_node, circle_dist):
    """ To Find the nearest nodes at max circle_dist from new_node in node_list from new_node  """
    nnode = len(node_list) + 1
    r = circle_dist * math.sqrt((math.log(nnode) / nnode))
    dist_list = [(node.x - new_node[0]) ** 2 +
                    (node.y - new_node[1]) ** 2 for node in node_list]
    near_inds = [dist_list.index(i) for i in dist_list if i <= r ** 2]
    return near_inds

class Node(object):
    """
    Coordinate representation in node form.
    x,y --> Coordinates
    Parent node is the node connected to the present node
    """

    def __init__(self, x, y):
            self.x = x
            self.y = y
            self.path_x = []
            self.path_y = []
            self.parent = None
            self.cost = 0.0

    def __str__(self):
        return ("("+str(self.x)+','+str(self.y)+")")


class RRTStar(object):
    """
    RRT star algorithm
    """

    def __init__(self, sample_area,
                    expand_dis=1.0,
                    path_resolution=1.0,
                    goal_sample_rate=0.1,
                    max_iter=250,
                    connect_circle_dist=20.0
                    ):
        """
        start: Start Point. in our case remains(0 , 0) unless specified
        goal: Next goal to be reached
        scan = LaserScan polar distances to Obstacles [r1,r2,r3...] initially assuming every scan occurs at 1 rad interval
        randomArea:Random Sampling Area
        """

        self.sample_area = sample_area
        self.sampler = sampler
        self.expand_dis = expand_dis
        self.goal_sample_rate = goal_sample_rate
        self.circle = connect_circle_dist
        self.max_iter = max_iter

    def __call__(self, goal_point, scan, start_point, animation=False):
        """Plans path from start to goal avoiding obstacles.
        Args:
            start_point: tuple with start point coordinates.
            end_point: tuple with end point coordinates.
            scan: list of obstacles which themselves are list of points
            animation: flag for showing planning visualization (default False)
        Returns:
            A list of points representing the path determined from
            start to goal while avoiding obstacles.
            An list containing just the start point means path could not be planned.
        """
        search_until_max_iter = True

        # Make line obstacles and scan in x,y from scan
        line_obstacles, pts = make_obstacles_scan(scan)

        # Setting Start and End
        a=start_point.point
        b=goal_point.point
        self.start = Node(a[0], a[1])
        self.goal = Node(b[0], b[1])

        # Initialize node with Starting Position
        self.node_list = [self.start]

        # Loop for maximum iterations to get the best possible path
        for iter in range(self.max_iter):
            #########################################
            # print("NODE_LIST-->")
            # for printer_i in self.node_list:
            #     print(printer_i)
            #########################################
            # Sample a Random point in the sample area
            rnd_point = sampler(self.sample_area, (self.goal.x , self.goal.y), self.goal_sample_rate)

            ########################################
            # print("RANDOM POINT-->")
            # print(rnd_point)
            ########################################

            # Find nearest node to the sampled point
            distance_list = [(node.x - rnd_point[0])**2 + (node.y -
                              rnd_point[1])**2 for node in self.node_list]
            nearest_node = self.node_list[distance_list.index(min(distance_list))]
            ########################################
            # print("NEAREST_NODE-->")
            # print(nearest_node.x , nearest_node.y , nearest_node.cost)
            ########################################
            # Creating a new Point in the Direction of sampled point
            theta = math.atan2(rnd_point[1] - nearest_node.y,
                               rnd_point[0] - nearest_node.x)
            new_point = nearest_node.x + self.expand_dis*math.cos(theta), \
                        nearest_node.y + self.expand_dis*math.sin(theta)
            
            #########################################
            # print("NEW_POINT-->")
            # print(new_point[0],new_point[1])
            #########################################
            # Check obstacle collision
            new_point = scan_obstacle_checker(scan, new_point)

            if math.isnan(new_point[0]):
                ########################################
                # print("ISNAN-->")
                # print(new_point)
                ########################################
                continue

            #If iterations is less than certain no. try exploring a bit    
            if iter<20:
                new_node = Node(new_point[0],new_point[1])
                new_node.parent = nearest_node
                new_node.cost = nearest_node.cost + math.sqrt((new_node.x-nearest_node.x)**2 + (new_node.y-nearest_node.y)**2)
                
                #Set the path for new node
                present_node = new_node
                px =[]
                py=[]
                while present_node.parent != None:
                    px.append(present_node.x)
                    py.append(present_node.y)
                    present_node = present_node.parent
                px.append(self.start.x)
                py.append(self.start.y)
                new_node.path_x = px[:]
                new_node.path_y = py[:]

                if animation and iter % 5 == 0:
                    self.draw_graph(scan, new_node)

                continue

            nearest_indexes = find_near_nodes(self.node_list, new_point, self.circle)

            # Getting the parent node from nearest indices

            costs = []  # List of Total costs from the start to new_node when attached to parent node in node_list
            temp_points = []

            for index in nearest_indexes:
                near_node = self.node_list[index]
                point_list = [(near_node.x , near_node.y), (new_point[0],new_point[1])]
                if not check_intersection_scan(point_list, line_obstacles):
                    costs.append(near_node.cost + math.sqrt((near_node.x - new_point[0])**2 + (near_node.y - new_point[1])**2))
                else:
                    costs.append(float("inf"))
            
            min_cost = min(costs)
            # Calculating the minimum cost and selecting the node for which it occurs as parent child

            if min_cost == float("inf"):
                continue

            # Setting the new node as the one with min cost
            min_ind = nearest_indexes[costs.index(min_cost)]
            new_node = Node(new_point[0],new_point[1])
            new_node.parent = self.node_list[min_ind]
            new_node.cost = min_cost

            #########################################
            # print("NEW_NODE-->")
            # print(new_node.x , new_node.y , new_node.cost)
            #########################################

            if new_node:
                    
                self.node_list.append(new_node)
                
                for ind in nearest_indexes:
                    node_check = self.node_list[ind]
                    point_list = [(new_node.x , new_node.y), (node_check.x , node_check.y)]
                    
                    no_coll = not check_intersection_scan(point_list, line_obstacles)
                    cost_improv = new_node.cost + math.sqrt((new_node.x - node_check.x)**2 + (new_node.y - node_check.y)**2) < node_check.cost

                    if no_coll and cost_improv:
                        node_check.parent = new_node

                present_node = new_node
                px =[]
                py=[]
                while present_node.parent != None:
                    px.append(present_node.x)
                    py.append(present_node.y)
                    present_node = present_node.parent
                px.append(self.start.x)
                py.append(self.start.y)
                new_node.path_x = px[:]
                new_node.path_y = py[:]
            if animation and iter % 5 == 0:
                self.draw_graph(scan, new_node)

            if (not search_until_max_iter) and new_node:  # check reaching the goal
                last_index = self.search_best_goal_node(scan)
                if last_index:
                    path = [[self.goal.x, self.goal.y]]
                    node = self.node_list[last_index]
                    while node.parent is not None:
                        path.append([node.x, node.y])
                        node = node.parent
                    path.append([node.x, node.y])
                    return path


        last_index = self.search_best_goal_node(scan)
        if last_index:
            path = [[self.goal.x, self.goal.y]]
            node = self.node_list[last_index]
            while node.parent is not None:
                path.append([node.x, node.y])
                node = node.parent
            path.append([node.x, node.y])
            return path
        return None

    def draw_graph(self, scan, rnd=None):
        plt.clf()
        pt_ang = np.arange(-0.521567881107,0.524276316166,0.00163668883033)
        pt_scan = np.array(scan)
        pts = []
        pt_x = np.multiply(pt_scan,np.cos(pt_ang))
        pt_y = np.multiply(pt_scan,np.sin(pt_ang))

        for a,b in zip(pt_x,pt_y):
            pts.append((a,b))

        if rnd is not None:
            plt.plot(rnd.x, rnd.y, "^k")
        for node in self.node_list:
            if node.parent:
                plt.plot(node.path_x, node.path_y, "-g")

        # for (ox, oy, size) in self.obstacle_list:
        #     self.plot_circle(ox, oy, size)
        plt.plot([x for (x, _) in pts], [y for (_, y) in pts],'r.')
        plt.plot(self.start.x, self.start.y, "xr")
        plt.plot(self.goal.x, self.goal.y, "xr")
        plt.axis("equal")
        plt.axis((-5,5,-5,5))
        plt.grid(True)
        plt.pause(0.01)

    def search_best_goal_node(self,scan):
        dist_to_goal_list = [math.sqrt(
            (n.x - self.goal.x)**2 + (n.y - self.goal.y)**2) for n in self.node_list]
        goal_inds = [dist_to_goal_list.index(
            i) for i in dist_to_goal_list if i <= self.expand_dis]

        safe_goal_inds = []
        for goal_ind in goal_inds:
            theta = math.atan2(
                self.node_list[goal_ind].y - self.goal.y, self.node_list[goal_ind].x - self.goal.x)

            t_node = Node(self.node_list[goal_ind].x + math.cos(theta) , self.node_list[goal_ind].y + math.sin(theta))
            if scan_obstacle_checker(scan , (t_node.x , t_node.y)):
                safe_goal_inds.append(goal_ind)

        if not safe_goal_inds:
            return None

        min_cost = min([self.node_list[i].cost for i in safe_goal_inds])
        for i in safe_goal_inds:
            if self.node_list[i].cost == min_cost:
                return i

        return None

def handle_add_two_ints(req):
    #print "Returning [%s + %s = %s]"%(req.a, req.b, (req.a + req.b))
    print("Start " + __file__)
    inf  = 100
    # ====Search Path with RRT====
    scan_list = req.scan_list
    scan_list = list(scan_list)
    for i in range(len(scan_list)):
        if(math.isnan(scan_list[i])):
            scan_list[i] = 100
    scan_list = tuple(scan_list)
    print("This is scan List ---------------------------------------------------->")
    print(len(scan_list))
    
   # if(rospy.get_time()-start_time<5):
	#list_of_obstacles=dynamic_obstacle_addition(list_of_obstacles,scan_list)
    #    start_time = rospy.get_time()

    # Set Initial parameters
    rrt_star = RRTStar(sample_area=[-50, 50])

    print('\n ' + '-'*30 +  "\n> Starting operation ...\n " + '-'*30 + '\n')
    start_time = time.time()


    path = rrt_star(goal_point = req.goal_pos, scan = scan_list, start_point= req.start_pos)
    print(path)
    print(type(path))
    l=[]
    for p in path:
        a=Point_xy()
        a.point=p
        l.append(a)
    b=PointArray()
    b.points=l
    if path is not None:
    	return PlannerResponse(b,True)
    else:
    	return PlannerResponse(b,False)

def add_two_ints_server():
    rospy.init_node('rrt_server')
    s = rospy.Service('rrt_planner', Planner, handle_add_two_ints)
    print "Ready."
    rospy.spin()

if __name__ == "__main__":
    add_two_ints_server()