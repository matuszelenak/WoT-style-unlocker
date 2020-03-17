import json
import os
import copy
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from io import BytesIO
from typing import List, Tuple

from flask import Flask, render_template, request, send_file

BASE_DIR = os.path.dirname(__file__)


class TankStylesApp(Flask):
    customizable_areas = {
        'GUN': 'Gun',
        'GUN GUN_2': 'Gun',
        'CHASSIS': 'Chassis',
        'TURRET': 'Turret',
        'HULL': 'Hull'
    }

    def __init__(self, *args, **kwargs):
        self.vehicles = defaultdict(lambda: {'script_paths': []})
        self.load_vehicle_scripts()
        super().__init__(*args, **kwargs)

    def load_vehicle_scripts(self):
        with open('source/display_names.json') as f:
            display_names = json.load(f)

        for root_dir, _, files in os.walk(os.path.join(BASE_DIR, 'source', 'res', 'scripts', 'item_defs', 'vehicles'), topdown=False):
            split_path = root_dir.split(os.sep)
            for file_name in files:
                with open(os.path.join(root_dir, file_name)) as f:
                    lines = f.readlines()
                    xml = ''.join(lines[:1] + lines[2:])

                root = ET.fromstring(xml)
                name, _ = os.path.splitext(root.tag)

                styles_set = set()
                for model_tag in root.iter(tag='models'):
                    model_styles = model_tag.find('sets')
                    if not model_styles:
                        continue

                    for style in list(model_styles):
                        styles_set.add((style.tag, display_names[name].get(style.tag, style.tag)))

                if not styles_set:
                    os.remove(os.path.join(root_dir, file_name))
                    continue

                camo, paint = set(), set()
                for areas in root.iter(tag='customizableVehicleAreas'):
                    camo_areas = areas.find('camouflage')
                    if camo_areas is not None and camo_areas.text:
                        camo.add(self.customizable_areas[camo_areas.text.strip()])

                    paint_areas = areas.find('paint')
                    if paint_areas is not None and paint_areas.text:
                        paint.add(self.customizable_areas[paint_areas.text.strip()])

                self.vehicles[name]['script_paths'].append(os.path.join(*split_path[-5:], file_name))
                self.vehicles[name].update({
                    'name': name,
                    'xml': xml,
                    'nation': split_path[-1],
                    'styles': list(styles_set),
                    'display_name': ' '.join(name.replace('_', ' ').split()[1:]),
                    'paint_areas': list(paint),
                    'camo_areas': list(camo)
                })

    def get_styled_xml(self, name, style_name, camos, paints):
        vehicle = self.vehicles[name]
        if style_name not in [codename for codename, name in vehicle['styles']]:
            return [], vehicle['xml']

        root = ET.fromstring(vehicle['xml'])
        model_states = ['undamaged', 'destroyed', 'exploded']
        for model_tag in root.iter(tag='models'):
            for state in model_states:
                model_tag.remove(model_tag.find(state))

            style_sets = model_tag.find('sets')
            if style_sets is None:
                raise ValueError
            style = style_sets.find(style_name)
            if style is None:
                raise ValueError

            for pos, state in enumerate(model_states):
                model_tag.insert(pos, copy.deepcopy(style.find(state)))

        for areas in root.iter(tag='customizableVehicleAreas'):
            camo_areas = areas.find('camouflage')
            if camo_areas is not None and camo_areas.text:
                key = self.customizable_areas[camo_areas.text.strip()]
                if key not in camos:
                    camo_areas.text = ''

            paint_areas = areas.find('paint')
            if paint_areas is not None and paint_areas.text:
                key = self.customizable_areas[paint_areas.text.strip()]
                if key not in paints:
                    paint_areas.text = ''

        return vehicle['script_paths'], ET.tostring(root).decode()


app = TankStylesApp(__name__)


def create_zip_file(files: List[Tuple[List[str], str]]):
    memory_file = BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_STORED) as archive:
        for filenames, content in files:
            for filename in filenames:
                archive.writestr(filename, content)

    memory_file.seek(0)
    return send_file(memory_file, attachment_filename='styles.wotmod', as_attachment=True)


def get_styled_files(form_data):
    included_vehicle_names = [key[len('include_'):] for key, value in form_data.items() if value == 'on']
    return [
        app.get_styled_xml(
            vehicle_name,
            form_data.get('style_' + vehicle_name),
            form_data.getlist('camo_' + vehicle_name) or [],
            form_data.getlist('paint_' + vehicle_name) or []
        )
        for vehicle_name in included_vehicle_names
    ]


@app.route('/', methods=['GET', 'POST'])
def styles():
    if request.method == 'POST':
        files = get_styled_files(request.form)
        if files:
            return create_zip_file(files)

    sorted_vehicles = sorted(app.vehicles.values(), key=lambda vehicle: (vehicle['nation'], vehicle['name']))
    return render_template('styles.html', vehicles=sorted_vehicles)


if __name__ == "__main__":
    app.run(debug=True, threaded=True, host='0.0.0.0', port=8000)
