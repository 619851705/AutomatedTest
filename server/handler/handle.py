# encoding:utf-8
import os
import tornado.web
import tornado.gen
from datetime import datetime
import xmlrpc.client
from bson.objectid import ObjectId
from . import config


class BaseHandler(tornado.web.RequestHandler):
	@property
	def db(self):
		return self.application.db


class HomeHandler(BaseHandler):
	def get(self):
		self.render("home.html")


class CasesHandler(BaseHandler):
	@staticmethod
	def get_case_items():
		case_items = []
		for case_path in config.CASES_DIR.iterdir():
			item = {}
			item["size"] = case_path.stat().st_size / 1024
			item["name"] = case_path.stem
			item["time"] = datetime.fromtimestamp(case_path.stat().st_mtime).strftime("%d/%m/%y %H:%M")
			case_items.append(item)
		return case_items

	@staticmethod
	def del_case(case_name):
		case_path = config.CASES_DIR.joinpath(case_name).with_suffix(".zip")
		if case_path.exists():
			os.remove(str(case_path))

	def post(self, param):
		if param == "upload":
			file_metas = self.request.files['file']

			for meta in file_metas:
				file_name = meta['filename']
				file_path = config.CASES_DIR.joinpath(file_name)
				with open(str(file_path), 'wb') as up:
					up.write(meta['body'])
		elif param == "del":
			case_name = self.get_argument("case_name")
			self.del_case(case_name)
		self.redirect("/cases/")

	def get(self, param):
		self.render("cases.html", case_items=self.get_case_items())


class MachinesHandler(BaseHandler):
	def add_machine(self, ip):
		tb_machine = self.db[config.TB_MACHINE]
		if not tb_machine.find_one({"ip": ip}):
			tb_machine.insert_one({"ip": ip})

	def del_machine(self, ip):
		tb_machine = self.db[config.TB_MACHINE]
		if tb_machine.find_one({"ip": ip}):
			tb_machine.remove({"ip": ip})

	def get_machine_state(self, ip):
		proxy = xmlrpc.client.ServerProxy("http://%s:8000/" % ip, verbose=True)
		try:
			running_state = proxy.proxy_running()
		except Exception as err:
			print(err)
			return -1
		return 1 if running_state else 0

	def get_machine_items(self):
		tb_machine = self.db[config.TB_MACHINE]
		machine_items = []
		for machine in tb_machine.find():
			machine["state"] = self.get_machine_state(machine["ip"])
			machine_items.append(machine)
		return machine_items

	def post(self, param):
		if param == "add":
			ip = self.get_argument("ip")
			self.add_machine(ip)
		elif param == "del":
			ip = self.get_argument("ip")
			self.del_machine(ip)
		self.redirect("/machines/")

	def get(self, param):
		machine_items = self.get_machine_items()
		self.render("machines.html", machine_items=machine_items)


class TasksHandler(BaseHandler):
	def add_task(self, version, cases, email):
		if not cases:
			return
		tb_task = self.db[config.TB_TASK]
		task_info = {
			"version": version,
			"cases": cases,
			"result": {},
			"time": datetime.now().strftime("%d/%m/%y %H:%M"),
			"email": email,
			"finished": False
		}
		tb_pending_case = self.db[config.TB_PENDING_CASE]
		task_id = tb_task.insert_one(task_info).inserted_id
		tb_pending_case.insert([{"name": case, "task_id": task_id, "version": version} for case in cases])

	def get_pending_cases(self):
		tb_task = self.db[config.TB_PENDING_CASE]
		return tb_task.find()

	def get_running_cases(self):
		tb_task = self.db[config.TB_RUNNING_CASE]
		return tb_task.find()

	def post(self, param):
		if param == "produce":
			version = self.get_argument("version")
			cases = self.get_arguments("cases")
			email = True if self.get_argument("email", None) else False
			self.add_task(version, cases, email)
		self.redirect("/tasks/")

	def get(self, param):
		case_items = CasesHandler.get_case_items()
		case_names = [case_item["name"] for case_item in case_items]
		self.render("tasks.html", case_names=case_names, pending_cases=self.get_pending_cases(),
		            running_cases=self.get_running_cases())


class ResultsHandler(BaseHandler):
	def get_finished_task_items(self):
		task_items = []
		tb_task = self.db[config.TB_TASK]
		for record in tb_task.find():
			if record["finished"]:
				task_items.append({"version": record["version"], "time": record["time"], "task_id": record["_id"]})
		return task_items

	def get_task(self, task_id):
		tb_task = self.db[config.TB_TASK]
		task = tb_task.find_one({"_id": ObjectId(task_id)})
		return task

	def get(self, param):
		param = param.strip()
		if not param:
			self.render("results.html", finished_task_items=self.get_finished_task_items())
		else:
			self.render("results_detail.html", task = self.get_task(param))