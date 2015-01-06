
from copy import deepcopy
import os, yaml, string
from math import degrees
from rospy import logerr, loginfo, get_param
import rospkg, genpy
import moveit_msgs.msg
from trajectory_msgs.msg import JointTrajectoryPoint
from sr_grasp.utils import mk_grasp
from sr_robot_msgs.msg import GraspArray

#http://code.activestate.com/recipes/66055-changing-the-indentation-of-a-multi-line-string/
def reindent(s, numSpaces):
    s = string.split(s, '\n')
    s = [(numSpaces * ' ') + line for line in s]
    s = string.join(s, '\n')
    return s

class Grasp(moveit_msgs.msg.Grasp):
    """
    Represents a single grasp, basically a wrapper around moveit_msgs/Grasp
    with added functions and Shadow Hand specific knowledge.
    """
    def __init__(self):
        super(Grasp, self).__init__()
        self.grasp_quality = 0.001
        self.joint_names = [
            'FFJ1', 'FFJ2', 'FFJ3', 'FFJ4',
            'LFJ1', 'LFJ2', 'LFJ3', 'LFJ4', 'LFJ5',
            'MFJ1', 'MFJ2', 'MFJ3', 'MFJ4',
            'RFJ1', 'RFJ2', 'RFJ3', 'RFJ4',
            'THJ1', 'THJ2', 'THJ3', 'THJ4', 'THJ5',
            'WRJ1', 'WRJ2']

        # Default the pre grasp to all 0.0
        zero_joints = dict.fromkeys(self.joint_names, 0.0)
        self.set_pre_grasp_point(zero_joints)

    @classmethod
    def from_msg(cls, msg):
        """Construct a shadow grasp object from moveit grasp object."""
        grasp = Grasp()
        grasp.id = msg.id
        grasp.pre_grasp_posture  = deepcopy(msg.pre_grasp_posture)
        grasp.grasp_posture      = deepcopy(msg.grasp_posture)
        grasp.grasp_pose         = deepcopy(msg.grasp_pose)
        grasp.grasp_quality      = msg.grasp_quality
        grasp.pre_grasp_approach = deepcopy(msg.pre_grasp_approach)
        grasp.post_grasp_retreat = deepcopy(msg.post_grasp_retreat)
        grasp.post_place_retreat = deepcopy(msg.post_place_retreat)
        grasp.max_contact_force  = msg.max_contact_force
        grasp.allowed_touch_objects = deepcopy(msg.allowed_touch_objects)
        return grasp

    def to_msg(self):
        """Return plain moveit_msgs/Grasp version of self."""
        raise Exception("TODO - to_msg")

    @classmethod
    def from_yaml(self, y):
        """
        Construct a shadow grasp object from YAML object. For example YAML
        grabbed from rostopic to a file.
        """
        grasp = Grasp()
        genpy.message.fill_message_args(grasp, y)
        return grasp

    def set_pre_grasp_point(self, *args, **kwargs):
        """
        Set the positions for a point (default 0) in the pre-grasp to a dict of
        joint positions.
        """
        self._set_posture_point(self.pre_grasp_posture, *args, **kwargs)

    def set_grasp_point(self, *args, **kwargs):
        """
        Set the positions for a point (default 0) in the grasp to a dict of
        joint positions.
        """
        self._set_posture_point(self.grasp_posture, *args, **kwargs)

    def get_grasp_point_positions(self, point=0):
        traj = self.grasp_posture
        joints = {}
        if len(traj.points) <= point + 1:
            for i in range(len(traj.joint_names)):
                joints[traj.joint_names[i]] = degrees(traj.points[point].positions[i])
        return joints

    def _set_posture_point(self, posture, positions, point=0):
        """Set the posture positions using a dict of joint positions."""
        # XXX: Why have we been doing this?
        #posture.header.stamp = now
        posture.joint_names = positions.keys()

        # Extend the array to be big enough.
        if len(posture.points) < point+1:
            for i in range(point+1):
                posture.points.append(JointTrajectoryPoint())

        # Update the point in place
        jtp = JointTrajectoryPoint()
        for name, pos in positions.iteritems():
            jtp.positions.append(pos)
        posture.points[point] = jtp

    # sr_hand compatibility
    @property
    def joints_and_positions(self):
        """
        Return dict of joint positions for the first grasp point. Empty dict
        if no grasp point set.
        """
        jp = {}
        if len(self.grasp_posture.points) > 0:
            for i,name in enumerate(self.grasp_posture.joint_names):
                jp[name] = degrees(self.grasp_posture.points[0].positions[i])
        return jp

    @joints_and_positions.setter
    def joints_and_positions(self, val):
        logerr("MIGRATION: You can no longer update the joints_and_positions dict directly. See the set_joint_and_position method.")

    def set_joint_and_position(self, name, val, point=0):
        joints = self.get_grasp_point_positions(point=point)
        joints[name] = val
        self.set_grasp_point(joints)

    @property
    def grasp_name(self): return self.id

    @grasp_name.setter
    def grasp_name(self, name): self.id = name


class GraspStash(object):
    """
    Interface to the list of grasps stored in a YAML file. Reads a parameter
    for the file name, so nodes can co-ordinate or can be given an explicit
    file path. You must call load_all() yourself, the constructor doesn't do
    that for you, it gives and empty stash. The default is to use grasps.xml
    from sr_grasp.
    """
    def __init__(self, grasps_file=None):
        # Store of all loaded grasps, indexed on grasp.id.
        self.grasps = {}

        # Set the YAML file to read and write grasps from.
        if grasps_file == None:
            rp = rospkg.RosPack()
            self.grasps_file = get_param('~grasps_file',
                    default = os.path.join(
                    rp.get_path('sr_grasp'), 'resource', 'grasps.yaml') )
        else:
            self.grasps_file = grasps_file

    def get_grasp_array(self):
        arr = GraspArray()
        arr.grasps = self.grasps.values()
        return arr

    def get_grasp_at(self, idx):
        """Return the Grasp at the given index."""
        return self.grasps.values()[idx]

    def size(self):
        """Return the number of grasps."""
        return len(self.grasps)

    def put_grasp(self, grasp):
        """Stash the given grasp, using it's id field, which must be set."""
        if grasp.id is None or grasp.id == "":
            raise Exception("Grasp has no id")
        # Up convert a plain grasp msg to our wrapper
        #if isinstance(grasp, moveit_msgs.msg.Grasp):
        #    grasp = Grasp.from_msg(grasp)
        self.grasps[grasp.id] = grasp

    def load_all(self):
        """Load all configured sources of grasps into the stash."""
        self.load_yaml_file(self.grasps_file)

    def as_yaml(self):
        return genpy.message.strify_message(self.get_grasp_array().grasps)

    def load_yaml_file(self, fname):
        """Load a set of grasps from a YAML file."""
        try:
            data = yaml.load(file(fname))
            self.load_yaml(data)
        except Exception as e:
            logerr("Failed to load YAML grasp file: %s error:%s"%(fname, e))
            return False
        else:
            loginfo("Loaded grasps from file: %s"%(fname))
            return True

    def load_yaml(self, data):
        """Load a set of grasps from a YAML object. Throws exceptions on errors."""
        for g in data:
            grasp = Grasp.from_yaml(g)
            self.put_grasp(grasp)

    def save_yaml_file(self, fname=""):
        if fname == "":
            fname = self.grasps_file
        with open(fname, "w") as txtfile:
            txtfile.write(self.as_yaml())

    # sr_hand compatibility interface
    # sr_hand side also access self.grasps as a dict
    def refresh(self):
        self.load_all()

    def write_grasp_to_file(self, grasp):
        stash = GraspStash(grasps_file=self.grasps_file)
        stash.load_all()
        stash.put_grasp(grasp)
        stash.save_yaml_file()

    def parse_tree(self, xmlfilename):
        self.load_all()