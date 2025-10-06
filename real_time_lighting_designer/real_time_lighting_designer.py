bl_info = {
    "name": "Real-Time Lighting Designer (Pro)",
    "author": "Wikz B",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Lighting Designer",
    "description": "Create, edit and save complex lighting setups with realtime Eevee preview and presets.",
    "category": "Lighting",
}

import bpy
from bpy.props import (
    StringProperty,
    BoolProperty,
    FloatProperty,
    FloatVectorProperty,
    EnumProperty,
    CollectionProperty,
    PointerProperty,
)
from bpy.types import (
    Panel,
    Operator,
    PropertyGroup,
    UIList,
)
import json

PREFIX = "RTLD_"  # prefix for lights created by the addon

# -----------------------------
# Helper functions
# -----------------------------

def _rtld_light_name(name):
    return f"{PREFIX}{name}"


def find_rtld_lights(context):
    return [ob for ob in context.scene.objects if ob.type == 'LIGHT' and ob.name.startswith(PREFIX)]


def create_light(context, name="Light", light_type='POINT'):
    data = bpy.data.lights.new(name=_rtld_light_name(name), type=light_type)
    obj = bpy.data.objects.new(_rtld_light_name(name), data)
    context.collection.objects.link(obj)
    return obj


def remove_light_obj(obj):
    # remove object and its data safely
    data = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    # if no users, remove light data
    if data and data.users == 0:
        bpy.data.lights.remove(data, do_unlink=True)


# -----------------------------
# Profiles and storage
# -----------------------------

class RTLDLightSpec(PropertyGroup):
    name: StringProperty()
    type: EnumProperty(
        name="Type",
        items=[('POINT', 'Point', ''), ('SUN', 'Sun', ''), ('SPOT', 'Spot', ''), ('AREA', 'Area', '')],
    )
    color: FloatVectorProperty(name="Color", subtype='COLOR', size=3, min=0.0, max=1.0)
    energy: FloatProperty(name="Energy", default=10.0)
    size: FloatProperty(name="Size", default=0.25)
    spot_size: FloatProperty(name="Spot Size", default=0.785398)
    use_shadow: BoolProperty(name="Shadow", default=True)
    location: FloatVectorProperty(name="Location", size=3)
    rotation: FloatVectorProperty(name="Rotation Euler", size=3)


class RTLDProfile(PropertyGroup):
    name: StringProperty(name="Profile Name")
    data_json: StringProperty(name="Data JSON")


# -----------------------------
# UIList of lights
# -----------------------------

class RTLD_UL_lights(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        # data is the scene property owner
        row = layout.row(align=True)
        lbl = item.name if item.name else "Light"
        row.prop(item, "name", text="")


# -----------------------------
# Scene properties container
# -----------------------------

class RTLDSceneProps(PropertyGroup):
    active_light_index: bpy.props.IntProperty(default=0)
    selected_light_name: StringProperty(default="")
    # UI quick controls
    realtime_preview: BoolProperty(name="Realtime Preview", default=True)
    engine: EnumProperty(
        items=[('BLENDER_EEVEE', 'Eevee', ''), ('CYCLES', 'Cycles', '')],
        name="Render Engine",
        default='BLENDER_EEVEE'
    )
    lights: CollectionProperty(type=RTLDLightSpec)
    profiles: CollectionProperty(type=RTLDProfile)
    profile_name: StringProperty(name="New Profile Name", default="NewProfile")


# -----------------------------
# Operators
# -----------------------------

class RTLD_OT_add_light(Operator):
    bl_idname = "rtld.add_light"
    bl_label = "Add Light"
    bl_description = "Add a new light managed by Lighting Designer"

    light_type: EnumProperty(
        items=[('POINT', 'Point', ''), ('SUN', 'Sun', ''), ('SPOT', 'Spot', ''), ('AREA', 'Area', '')],
        name="Type",
        default='POINT'
    )

    def execute(self, context):
        scene = context.scene
        obj = create_light(context, name=f"{self.light_type}", light_type=self.light_type)
        # default transform
        obj.location = context.scene.cursor.location
        # add to scene props list
        light_spec = scene.rtld_props.lights.add()
        light_spec.name = obj.name
        light_spec.type = self.light_type
        light_spec.color = tuple(obj.data.color)
        light_spec.energy = obj.data.energy
        light_spec.size = getattr(obj.data, 'size', 0.25)
        light_spec.spot_size = getattr(obj.data, 'spot_size', 0.785398)
        light_spec.use_shadow = obj.data.use_shadow
        light_spec.location = obj.location
        light_spec.rotation = obj.rotation_euler
        scene.rtld_props.active_light_index = len(scene.rtld_props.lights) - 1
        scene.rtld_props.selected_light_name = obj.name
        return {'FINISHED'}


class RTLD_OT_remove_light(Operator):
    bl_idname = "rtld.remove_light"
    bl_label = "Remove Light"
    bl_description = "Remove selected RTLD light"

    @classmethod
    def poll(cls, context):
        return len(context.scene.rtld_props.lights) > 0

    def execute(self, context):
        scene = context.scene
        idx = scene.rtld_props.active_light_index
        if idx < 0 or idx >= len(scene.rtld_props.lights):
            return {'CANCELLED'}
        name = scene.rtld_props.lights[idx].name
        # find object
        obj = bpy.data.objects.get(name)
        if obj:
            remove_light_obj(obj)
        scene.rtld_props.lights.remove(idx)
        scene.rtld_props.active_light_index = max(0, min(idx - 1, len(scene.rtld_props.lights) - 1))
        return {'FINISHED'}


class RTLD_OT_sync_from_scene(Operator):
    bl_idname = "rtld.sync_from_scene"
    bl_label = "Sync From Scene"
    bl_description = "Find RTLD lights in the scene and populate the listing"

    def execute(self, context):
        scene = context.scene
        scene.rtld_props.lights.clear()
        for ob in find_rtld_lights(context):
            ls = scene.rtld_props.lights.add()
            ls.name = ob.name
            ls.type = ob.data.type
            ls.color = tuple(ob.data.color)
            ls.energy = ob.data.energy
            ls.size = getattr(ob.data, 'size', 0.25)
            ls.spot_size = getattr(ob.data, 'spot_size', 0.785398)
            ls.use_shadow = ob.data.use_shadow
            ls.location = ob.location
            ls.rotation = ob.rotation_euler
        return {'FINISHED'}


class RTLD_OT_apply_light_props(Operator):
    bl_idname = "rtld.apply_light_props"
    bl_label = "Apply Light Properties"
    bl_description = "Apply property values from the UI to the actual Blender light"

    @classmethod
    def poll(cls, context):
        scene = context.scene
        idx = scene.rtld_props.active_light_index
        return 0 <= idx < len(scene.rtld_props.lights)

    def execute(self, context):
        scene = context.scene
        idx = scene.rtld_props.active_light_index
        spec = scene.rtld_props.lights[idx]
        obj = bpy.data.objects.get(spec.name)
        if obj is None:
            self.report({'WARNING'}, "Light object not found in scene")
            return {'CANCELLED'}
        ld = obj.data
        ld.type = spec.type
        ld.color = spec.color
        ld.energy = spec.energy
        # some types have specific attrs
        try:
            ld.size = spec.size
        except Exception:
            pass
        try:
            ld.spot_size = spec.spot_size
        except Exception:
            pass
        ld.use_shadow = spec.use_shadow
        obj.location = spec.location
        obj.rotation_euler = spec.rotation
        return {'FINISHED'}


class RTLD_OT_apply_preset(Operator):
    bl_idname = "rtld.apply_preset"
    bl_label = "Apply Preset"
    bl_description = "Apply a built-in preset lighting setup"

    preset: EnumProperty(
        items=[
            ('THREE_POINT', '3-Point (Key/Fill/Rim)', ''),
            ('CINEMATIC', 'Cinematic', ''),
            ('SUNSET', 'Sunset', ''),
            ('STUDIO', 'Studio / Soft', ''),
            ('COOL_AMBIENT', 'Cool Ambient', ''),
        ],
        default='THREE_POINT'
    )

    def execute(self, context):
        # clear existing RTLD lights
        for ob in list(find_rtld_lights(context)):
            remove_light_obj(ob)
        context.scene.rtld_props.lights.clear()

        if self.preset == 'THREE_POINT':
            # Key
            key = create_light(context, name='Key', light_type='SPOT')
            key.location = (2.5, -2.0, 2.0)
            key.rotation_euler = (0.9, 0.0, 2.3)
            key.data.energy = 1200
            key.data.color = (1.0, 0.95, 0.9)
            key.data.spot_size = 0.9
            # Fill
            fill = create_light(context, name='Fill', light_type='AREA')
            fill.location = (-2.0, -1.5, 1.5)
            fill.rotation_euler = (1.1, 0.0, -0.5)
            fill.data.energy = 400
            fill.data.size = 1.5
            fill.data.color = (0.9, 0.95, 1.0)
            # Rim
            rim = create_light(context, name='Rim', light_type='SUN')
            rim.location = (-3.0, 3.0, 4.0)
            rim.data.energy = 3.0
            rim.data.color = (1.0, 0.8, 0.6)

            created = [key, fill, rim]

        elif self.preset == 'CINEMATIC':
            key = create_light(context, name='CineKey', light_type='SPOT')
            key.location = (4.0, -3.0, 3.0)
            key.data.energy = 1600
            key.data.color = (1.0, 0.85, 0.78)
            key.data.spot_size = 0.6

            rim = create_light(context, name='CineRim', light_type='SUN')
            rim.location = (-4.0, 4.0, 6.0)
            rim.data.energy = 2.5
            rim.data.color = (1.0, 0.5, 0.3)

            fill = create_light(context, name='CineFill', light_type='AREA')
            fill.location = (-1.5, -2.0, 1.4)
            fill.data.energy = 300
            fill.data.size = 1.8

            created = [key, rim, fill]

        elif self.preset == 'SUNSET':
            sun = create_light(context, name='SunsetSun', light_type='SUN')
            sun.data.energy = 5.0
            sun.data.color = (1.0, 0.4, 0.2)
            sun.rotation_euler = (0.9, 0.0, -0.7)

            warm_fill = create_light(context, name='WarmFill', light_type='AREA')
            warm_fill.location = (-2.0, -1.0, 1.2)
            warm_fill.data.energy = 200
            warm_fill.data.color = (1.0, 0.6, 0.5)

            created = [sun, warm_fill]

        elif self.preset == 'STUDIO':
            # Soft large area lights
            left = create_light(context, name='StudioLeft', light_type='AREA')
            left.location = (3.0, -1.0, 2.5)
            left.data.size = 3.0
            left.data.energy = 800

            right = create_light(context, name='StudioRight', light_type='AREA')
            right.location = (-3.0, -1.0, 2.5)
            right.data.size = 3.0
            right.data.energy = 650

            rim = create_light(context, name='StudioRim', light_type='SPOT')
            rim.location = (0.0, 5.0, 3.0)
            rim.data.energy = 300
            rim.data.spot_size = 1.2

            created = [left, right, rim]

        elif self.preset == 'COOL_AMBIENT':
            amb = create_light(context, name='CoolAmb', light_type='AREA')
            amb.data.energy = 150
            amb.data.color = (0.6, 0.8, 1.0)
            amb.location = (0.0, -2.0, 2.0)
            created = [amb]

        else:
            created = []

        # add to scene props
        for ob in created:
            ls = context.scene.rtld_props.lights.add()
            ls.name = ob.name
            ls.type = ob.data.type
            ls.color = tuple(ob.data.color)
            ls.energy = ob.data.energy
            ls.size = getattr(ob.data, 'size', 0.25)
            ls.spot_size = getattr(ob.data, 'spot_size', 0.785398)
            ls.use_shadow = ob.data.use_shadow
            ls.location = ob.location
            ls.rotation = ob.rotation_euler

        context.scene.rtld_props.active_light_index = 0
        return {'FINISHED'}


class RTLD_OT_save_profile(Operator):
    bl_idname = "rtld.save_profile"
    bl_label = "Save Profile"
    bl_description = "Save current RTLD lights to a named profile"

    @classmethod
    def poll(cls, context):
        return len(context.scene.rtld_props.lights) > 0

    def execute(self, context):
        scene = context.scene
        name = scene.rtld_props.profile_name.strip()
        if not name:
            self.report({'WARNING'}, "Please set a profile name")
            return {'CANCELLED'}
        profile = scene.rtld_props.profiles.add()
        profile.name = name
        # Build a JSON array of lights
        arr = []
        for ls in scene.rtld_props.lights:
            arr.append({
                'name': ls.name,
                'type': ls.type,
                'color': list(ls.color),
                'energy': ls.energy,
                'size': ls.size,
                'spot_size': ls.spot_size,
                'use_shadow': ls.use_shadow,
                'location': list(ls.location),
                'rotation': list(ls.rotation),
            })
        profile.data_json = json.dumps(arr)
        self.report({'INFO'}, f"Profile '{name}' saved")
        return {'FINISHED'}


class RTLD_OT_load_profile(Operator):
    bl_idname = "rtld.load_profile"
    bl_label = "Load Profile"
    bl_description = "Load lights from a saved profile (replaces current RTLD lights)"

    index: bpy.props.IntProperty()

    def execute(self, context):
        scene = context.scene
        if self.index < 0 or self.index >= len(scene.rtld_props.profiles):
            return {'CANCELLED'}
        prof = scene.rtld_props.profiles[self.index]
        try:
            arr = json.loads(prof.data_json)
        except Exception as e:
            self.report({'ERROR'}, f"Profile data corrupted: {e}")
            return {'CANCELLED'}
        # Remove current RTLD lights
        for ob in list(find_rtld_lights(context)):
            remove_light_obj(ob)
        scene.rtld_props.lights.clear()

        for item in arr:
            ob = create_light(context, name=item.get('name', 'ProfileLight'), light_type=item.get('type', 'POINT'))
            ob.data.color = tuple(item.get('color', [1.0, 1.0, 1.0]))
            ob.data.energy = item.get('energy', 10.0)
            try:
                ob.data.size = item.get('size', 0.25)
            except Exception:
                pass
            try:
                ob.data.spot_size = item.get('spot_size', 0.785398)
            except Exception:
                pass
            ob.data.use_shadow = item.get('use_shadow', True)
            ob.location = tuple(item.get('location', [0.0, 0.0, 0.0]))
            ob.rotation_euler = tuple(item.get('rotation', [0.0, 0.0, 0.0]))
            ls = scene.rtld_props.lights.add()
            ls.name = ob.name
            ls.type = ob.data.type
            ls.color = tuple(ob.data.color)
            ls.energy = ob.data.energy
            ls.size = getattr(ob.data, 'size', 0.25)
            ls.spot_size = getattr(ob.data, 'spot_size', 0.785398)
            ls.use_shadow = ob.data.use_shadow
            ls.location = ob.location
            ls.rotation = ob.rotation_euler

        scene.rtld_props.active_light_index = 0
        self.report({'INFO'}, f"Profile '{prof.name}' loaded")
        return {'FINISHED'}


class RTLD_OT_delete_profile(Operator):
    bl_idname = "rtld.delete_profile"
    bl_label = "Delete Profile"
    bl_description = "Delete selected profile"

    index: bpy.props.IntProperty()

    def execute(self, context):
        scene = context.scene
        if 0 <= self.index < len(scene.rtld_props.profiles):
            scene.rtld_props.profiles.remove(self.index)
            return {'FINISHED'}
        return {'CANCELLED'}


# -----------------------------
# Panel UI
# -----------------------------

class RTLD_PT_panel(Panel):
    bl_label = "Lighting Designer"
    bl_category = "Lighting Designer"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        props = scene.rtld_props

        row = layout.row(align=True)
        row.operator('rtld.sync_from_scene', text='Sync From Scene')
        row.operator('rtld.add_light', text='Add').light_type = 'POINT'
        row.operator('rtld.apply_preset', text='Presets').preset = 'THREE_POINT'

        # Presets menu (drop down)
        box = layout.box()
        box.label(text="Presets")
        row = box.row(align=True)
        row.operator('rtld.apply_preset', text='3-Point').preset = 'THREE_POINT'
        row.operator('rtld.apply_preset', text='Cinematic').preset = 'CINEMATIC'
        row = box.row(align=True)
        row.operator('rtld.apply_preset', text='Studio').preset = 'STUDIO'
        row.operator('rtld.apply_preset', text='Sunset').preset = 'SUNSET'
        row = box.row(align=True)
        row.operator('rtld.apply_preset', text='Cool Ambient').preset = 'COOL_AMBIENT'

        # Engine toggle and realtime
        box = layout.box()
        box.label(text="Settings")
        row = box.row()
        row.prop(props, 'realtime_preview')
        row = box.row()
        row.prop(props, 'engine', text='Render')
        row.operator('rtld.set_engine', text='Apply Engine')

        # Light list
        box = layout.box()
        box.label(text="Managed Lights")
        row = box.row()
        row.template_list('RTLD_UL_lights', '', props, 'lights', props, 'active_light_index', rows=4)
        col = row.column(align=True)
        col.operator('rtld.add_light', text='', icon='ADD').light_type = 'POINT'
        col.operator('rtld.remove_light', text='', icon='REMOVE')
        col.operator('rtld.apply_light_props', text='', icon='CHECKMARK')

        # Selected light properties
        if 0 <= props.active_light_index < len(props.lights):
            sel = props.lights[props.active_light_index]
            box = layout.box()
            box.label(text=f"Edit: {sel.name}")
            box.prop(sel, 'name')
            box.prop(sel, 'type')
            box.prop(sel, 'color')
            box.prop(sel, 'energy')
            box.prop(sel, 'size')
            box.prop(sel, 'spot_size')
            box.prop(sel, 'use_shadow')
            box.prop(sel, 'location')
            box.prop(sel, 'rotation')
            box.operator('rtld.apply_light_props', text='Apply to Scene')

        # Profiles
        box = layout.box()
        box.label(text="Profiles")
        row = box.row(align=True)
        row.prop(props, 'profile_name')
        row.operator('rtld.save_profile', text='Save')
        for i, p in enumerate(props.profiles):
            r = box.row(align=True)
            r.label(text=p.name)
            op = r.operator('rtld.load_profile', text='Load')
            op.index = i
            delop = r.operator('rtld.delete_profile', text='', icon='X')
            delop.index = i

        # Quick tips
        layout.separator()
        layout.label(text="Tip: Use 'Sync From Scene' to import existing RTLD_ lights")


# -----------------------------
# Small operator to set render engine
# -----------------------------

class RTLD_OT_set_engine(Operator):
    bl_idname = 'rtld.set_engine'
    bl_label = 'Set Engine'

    def execute(self, context):
        scene = context.scene
        scene.render.engine = scene.rtld_props.engine
        self.report({'INFO'}, f"Render engine set to {scene.render.engine}")
        return {'FINISHED'}


# -----------------------------
# Handlers / updates
# -----------------------------

def realtime_update(scene):
    props = scene.rtld_props
    if not props.realtime_preview:
        return
    # push UI props into actual objects
    for ls in props.lights:
        obj = bpy.data.objects.get(ls.name)
        if not obj:
            continue
        ld = obj.data
        try:
            # only sync a few properties to keep realtime responsiveness
            ld.color = ls.color
            ld.energy = ls.energy
            ld.use_shadow = ls.use_shadow
            if hasattr(ld, 'size'):
                ld.size = ls.size
            if hasattr(ld, 'spot_size'):
                ld.spot_size = ls.spot_size
            obj.location = ls.location
            obj.rotation_euler = ls.rotation
        except Exception:
            pass


# -----------------------------
# Registration
# -----------------------------

classes = (
    RTLDLightSpec,
    RTLDProfile,
    RTLDSceneProps,
    RTLD_UL_lights,
    RTLD_OT_add_light,
    RTLD_OT_remove_light,
    RTLD_OT_sync_from_scene,
    RTLD_OT_apply_light_props,
    RTLD_OT_apply_preset,
    RTLD_OT_save_profile,
    RTLD_OT_load_profile,
    RTLD_OT_delete_profile,
    RTLD_PT_panel,
    RTLD_OT_set_engine,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.rtld_props = PointerProperty(type=RTLDSceneProps)
    # add handler
    if realtime_update not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(realtime_update)


def unregister():
    # remove handler
    if realtime_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(realtime_update)
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
    del bpy.types.Scene.rtld_props


if __name__ == '__main__':
    register()
