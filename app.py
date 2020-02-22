import os
import copy
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from io import BytesIO
from typing import List, Tuple

from flask import Flask, render_template, request, send_file
from flask_bootstrap import Bootstrap


BASE_DIR = os.path.dirname(__file__)


class TankStylesApp(Flask):
    def __init__(self, *args, **kwargs):
        self.vehicles = defaultdict(lambda: {'script_paths': []})
        self.load_vehicle_scripts()
        super().__init__(*args, **kwargs)

    def load_vehicle_scripts(self):
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
                        styles_set.add(style.tag)

                if not styles_set:
                    continue

                self.vehicles[name]['script_paths'].append(os.path.join(*split_path[-5:], file_name))
                self.vehicles[name].update({
                    'name': name,
                    'xml': xml,
                    'nation': split_path[-1],
                    'styles': list(styles_set),
                    'display_name': ' '.join(name.replace('_', ' ').split()[1:])
                })

    def get_styled_xml(self, name, style_name):
        vehicle = self.vehicles[name]
        if style_name not in vehicle['styles']:
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

        return vehicle['script_paths'], ET.tostring(root).decode()


app = TankStylesApp(__name__)
Bootstrap(app)


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
    return [app.get_styled_xml(vehicle_name, form_data.get('style_' + vehicle_name)) for vehicle_name in included_vehicle_names]


@app.route('/', methods=['GET', 'POST'])
def styles():
    if request.method == 'POST':
        files = get_styled_files(request.form)
        return create_zip_file(files)

    sorted_vehicles = sorted(app.vehicles.values(), key=lambda vehicle: (vehicle['nation'], vehicle['name']))
    return render_template('styles.html', vehicles=sorted_vehicles)


if __name__ == "__main__":
    app.run(debug=True, threaded=True, host='0.0.0.0', port=8000)
