# Copyright (C) 2024 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions
# and limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

from enum import Enum

import docker
import py_trees
from scenario_execution.actions.base_action import BaseAction


class ExecutionStatus(Enum):
    IDLE = 1
    FOUND_CONTAINER = 2
    EXECUTING = 3
    DONE = 4


class DockerExec(BaseAction):
    """
    Run a command inside a container
    """

    def __init__(self, container: str, command: str,
                 environment: list, privileged: bool,
                 user: str, workdir: str):
        super().__init__()
        self.container = container
        self.command = command
        self.environment = environment
        self.privileged = privileged
        self.user = user
        self.workdir = workdir

        self.client = None
        self.container_object = None
        self.execution_instance = None
        self.execution_output = None
        self.current_state = ExecutionStatus.IDLE

    def setup(self, **kwargs):
        # create docker client
        self.client = docker.from_env()

    def update(self) -> py_trees.common.Status:
        if self.current_state == ExecutionStatus.IDLE:
            try:
                self.container_object = self.client.containers.get(self.container)
                self.current_state = ExecutionStatus.FOUND_CONTAINER
            except docker.errors.APIError as e:
                self.feedback_message = f"Docker container {self.container} not yet running {e}"  # pylint: disable= attribute-defined-outside-init
                return py_trees.common.Status.RUNNING

        if self.current_state == ExecutionStatus.FOUND_CONTAINER:
            try:
                self.execution_instance = self.client.api.exec_create(
                    self.container_object.id,
                    self.command,
                    environment=self.environment,
                    privileged=self.privileged,
                    user=self.user,
                    workdir=self.workdir)

                self.execution_output = self.client.api.exec_start(
                    self.execution_instance['Id'],
                    tty=False,
                    stream=True
                )
                self.current_state = ExecutionStatus.EXECUTING
                self.feedback_message = f"Executing '{self.command}' in container {self.container}"  # pylint: disable= attribute-defined-outside-init
            except docker.errors.APIError as e:
                self.feedback_message = f"Docker exec of command '{self.command}' failed: {e}"  # pylint: disable= attribute-defined-outside-init
                return py_trees.common.Status.FAILURE

        if self.current_state == ExecutionStatus.EXECUTING:
            try:
                log = next(self.execution_output)
                self.feedback_message = f"Executing '{self.command}' in container {self.container} with output: {log.decode()}"  # pylint: disable= attribute-defined-outside-init
            except StopIteration:
                self.current_state = ExecutionStatus.DONE

        if self.current_state == ExecutionStatus.DONE:
            exit_metadata = self.client.api.exec_inspect(self.execution_instance['Id'])
            assert not exit_metadata['Running']
            exit_code = exit_metadata['ExitCode']
            if exit_code == 0:
                self.feedback_message = f"Finished execution of '{self.command}' in container {self.container}"  # pylint: disable= attribute-defined-outside-init
                return py_trees.common.Status.SUCCESS
            else:
                self.feedback_message = f"Execution of '{self.command}' in container {self.container} failed"  # pylint: disable= attribute-defined-outside-init
                return py_trees.common.Status.FAILURE

        return py_trees.common.Status.RUNNING
