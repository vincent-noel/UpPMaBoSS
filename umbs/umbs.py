import os
import sys
import re
import random
import subprocess
import pandas as pd

class UpP_MaBoSS:
    def __init__(self, model, uppfile, workdir, previous_run=None, verbose=False):

        self.workdir = workdir
        self.model = model
        self.uppfile = uppfile
        self.bndfile = os.path.join(workdir, 'model.bnd')
        self.cfgfile = os.path.join(workdir, 'model.cfg')
        self.time_step = model.param['max_time']
        self.time_shift = 0
        self.base_ratio = 1

        self.node_list = []
        self.division_node = ""
        self.death_node = ""
        self.MaBoSS_exec = ""
        self.update_var = {}
        self.pop_ratio = 1.0
        self.step_number = -1

        self.verbose = verbose
        
        self.pop_ratios = None
        
        if previous_run:
            # Chain the results!!
            prev_pop_ratios = previous_run.get_population_ratios()
            self.time_shift = prev_pop_ratios.last_valid_index()
            self.base_ratio = prev_pop_ratios.iloc[-1]
            self.model = model.copy()
        
        if not os.path.exists(workdir):
            # Load the previous run final state
            if previous_run: _get_next_condition_from_trajectory(previous_run, self.model)
            
            # Prepare the new run
            os.makedirs(workdir)
            with open( self.bndfile, 'w' ) as out:
                self.model.print_bnd(out)
            with open( self.cfgfile, 'w' ) as out:
                self.model.print_cfg(out)
            
            self._run()

    def _run(self):

        self._getNodeList()
        self._readUppFile()

        if self.MaBoSS_exec == "":
            self.MaBoSS_exec = "./MaBoSS"

        outName = os.path.splitext(self.cfgfile)[0]

        with open(outName+"_PopR.csv", "w") as PopRatioF, open(outName+"_PopProbTraj.csv", "w") as ResumeFile:
            PopRatioF.write("Step\tPopRatio\n")
            if self.verbose:
                print("Run MaBoSS step 0")

            subprocess.call([self.MaBoSS_exec, "-c", self.cfgfile, "-o", outName+"_Step_0", self.bndfile])
            PopRatioF.write("0\t%g\n" % self.pop_ratio)

            with open(outName+"_Step_0_probtraj.csv", "r") as FirstPTrjF:
                line = FirstPTrjF.readline().split("\t", 1)[1]
                ResumeFile.write("Step\tPopRatio\t%s\n" % line)

            cfgFileStep = self.cfgfile

            for stepIndex in range(1, self.step_number+1):

                LastLinePrevTraj = ""
                with open("%s_Step_%d_probtraj.csv" % (outName, stepIndex-1), 'r') as PrStepTrajF:
                    LastLinePrevTraj = PrStepTrajF.readlines()[-1]

                self.pop_ratio *= self._updatePopRatio(LastLinePrevTraj)
                PopRatioF.write("%d\t%g\n" % (stepIndex, self.pop_ratio))

                line4ResFile = LastLinePrevTraj.split("\t", 1)[1]
                ResumeFile.write("%d\t%g\t%s" % (stepIndex, self.pop_ratio, line4ResFile))

                cfgFileStep = self._buildUpdateCfg(cfgFileStep, LastLinePrevTraj)
                if cfgFileStep == "":
                    if self.verbose:
                        print("No cells left")

                    break

                else:
                    if self.verbose:
                        print("Running MaBoSS for step %d" % stepIndex)

                    subprocess.call([self.MaBoSS_exec, 
                        "-c", cfgFileStep, 
                        "-o", "%s_Step_%d" % (outName, stepIndex),
                        self.bndfile
                    ])

    def get_population_ratios(self, name=None):
        if self.pop_ratios is None:
            raw_pop_ratios = []
            with open(self.cfgfile.replace(".cfg","_PopR.csv")) as f:
                f.readline()
                for line in f:
                    data = line.strip('\n').split("\t")
                    raw_pop_ratios.append(self.base_ratio * float(data[1]))
            time_steps = [ self.time_shift + self.time_step*t for t in range(len(raw_pop_ratios)) ]
            self.pop_ratios = pd.Series(raw_pop_ratios, index=time_steps)
        if name: self.pop_ratios.name = name
        return self.pop_ratios

    def _getNodeList(self):

        try:
            with open(self.bndfile, 'r') as BND:
                for line in BND.readlines():
                    if "node" in line or "Node" in line:
                        tokens = line.split()
                        self.node_list.append(tokens[1])

        except FileNotFoundError:
            print("Cannot find .bnd file", file=sys.stderr)
            exit()

    def _readUppFile(self):

        try:
            with open(self.uppfile, 'r') as UPP:
                for line in UPP.readlines():
                    
                    if line.startswith("death"):
                        
                        if self.death_node != "":
                            print("Multiple definition of death node", file=sys.stderr)
                            exit()

                        self.death_node = line.split("=")[1]
                        self.death_node = self.death_node.replace(";", "").strip()
                       
                        if self.verbose:
                            print("Death node : %s" % self.death_node)

                    if line.startswith("division"):
                        
                        if self.division_node != "":
                            print("Multiple definition of division node", file=sys.stderr)
                            exit()

                        self.division_node = line.split("=")[1]
                        self.division_node = self.division_node.replace(";", "").strip()
                        
                        if self.verbose:
                            print("Division node : %s" % self.division_node)

                    if line.startswith("steps"):
                        
                        if self.step_number != -1:
                            print("Multiple definition of step number", file=sys.stderr)
                            exit()

                        self.step_number = line.split("=")[1]
                        self.step_number = int(self.step_number.replace(";", "").strip())
                        
                        if self.verbose:
                            print("Number of steps : %s" % self.step_number)
            
                    if line.startswith("MaBoSS"):
                        
                        if self.MaBoSS_exec != "":
                            print("Multiple definition of MaBoSS executable", file=sys.stderr)
                            exit()

                        self.MaBoSS_exec = line.split("=")[1]
                        self.MaBoSS_exec = self.MaBoSS_exec.replace(";", "").strip()
                        
                        if self.verbose:
                            print("MaBoSS executable : %s" % self.MaBoSS_exec)
            
                    if line.startswith("$"):

                        (varName, value) = line.split("u=", 1)
                        varName = varName.strip()
                        if varName in self.update_var.keys():
                            print("Multiple definitions of %s" % varName)
                            exit()


                        value = value.replace(";", "").strip()
                        self.update_var.update({varName: value})
                        
                        if self.verbose:
                            print("Var %s updated by value %s" % (varName, value))

        except FileNotFoundError:
            print("Cannot find .upp file", file=sys.stderr)
            exit()

    def _buildUpdateCfg(self, last_cfg_file, prob_traj_line): 

        probTrajListFull = prob_traj_line.split("\t")
        probTrajList = probTrajListFull.copy()

        for prob_traj in probTrajListFull:
            if prob_traj[0].isalpha() or prob_traj == "<nil>":
                break
            else:
                probTrajList.pop(0)
            
        normFactor = 0
        deathProb = 0
        divisionProb = 0

        for i in range(0, len(probTrajList), 3):
            t_state = probTrajList[i]

            if nodeIsInState(self.death_node, t_state):
                deathProb += float(probTrajList[i+1])
                probTrajList[i+1] = str(0)

            else:
                if t_state == self.division_node:
                    divisionProb += float(probTrajList[i+1])
                    probTrajList[i+1] = str(2*float(probTrajList[i+1]))
                    probTrajList[i] = "<nil>"

                elif t_state.startswith(self.division_node+" "):
                    divisionProb += float(probTrajList[i+1])
                    probTrajList[i+1] = str(2*float(probTrajList[i+1]))
                    probTrajList[i] = probTrajList[i].replace(self.division_node+" -- ", "")

                elif (" %s " % self.division_node) in t_state:
                    divisionProb += float(probTrajList[i+1])
                    probTrajList[i+1] = str(2*float(probTrajList[i+1]))
                    probTrajList[i] = probTrajList[i].replace(" -- "+self.division_node, "")
            
                elif t_state.endswith(" "+self.division_node):
                    divisionProb += float(probTrajList[i+1])
                    probTrajList[i+1] = str(2*float(probTrajList[i+1]))
                    probTrajList[i] = probTrajList[i].replace(" -- "+self.division_node, "")

                normFactor += float(probTrajList[i+1])

        if self.verbose:
            print("Norm Factor:%g probability of death: %g probability of division: %g" % (normFactor, deathProb, divisionProb))

        if normFactor == 0:
            # All cells are dead
            return "" 

        else:
            # Construct new .cfg file
            for i in range(0, len(probTrajList), 3):
                probTrajList[i+1] = str(float(probTrajList[i+1])/normFactor)

            newCfgFile = ""
            t_line = last_cfg_file.split("_Step_")
            if len(t_line) > 2:
                print("Do not use the word \"Step\" in the name of the .cfg file", file=sys.stderr)
                exit()

            elif len(t_line) == 1:
                t_name = os.path.splitext(last_cfg_file)[0]
                newCfgFile = "%s_Step_1.cfg" % t_name

            else:
                t_step = int(os.path.splitext(t_line[1])[0])
                newCfgFile = "%s_Step_%d.cfg" % (t_line[0], t_step+1)

            with open(last_cfg_file, 'r') as LastCFG, open(newCfgFile, 'w') as NewCFG:
                for line in LastCFG.readlines():
                    if not "istate" in line:
                        upVar = ""
                        for testUpVar in self.update_var.keys():
                            t_testUpVar = testUpVar.replace("$", "")
                            if line.startswith("$"+t_testUpVar):
                                upVar = "$"+t_testUpVar

                        if upVar == "":
                            NewCFG.write(line)

                        else:
                            updateVarLine = varDef_Upp(self.update_var[upVar], probTrajList)

                            for match in re.findall("#rand", updateVarLine):
                                rand_number = random.uniform(0, 1)
                                updateVarLine = updateVarLine.replace("#rand", str(rand_number), 1)
                            
                            updateVarLine = updateVarLine.replace("#pop_ratio", str(self.pop_ratio))
                            NewCFG.write("%s = %s\n" % (upVar, updateVarLine))
                           
                            if self.verbose:
                                print("Updated variable: %s = %s" % (upVar, updateVarLine))

                initLine = self._initCond_Trajline(probTrajList)
                NewCFG.write(initLine+"\n")

        return newCfgFile
        
    def _updatePopRatio(self, last_line):

        upPopRatio = 0.0
        probTrajList = last_line.split("\t")
        indexStateTrajList = -1

        for probTraj in probTrajList:
            indexStateTrajList += 1
            if probTraj[0].isalpha() or probTraj == "<nil>":
                break

        for i in range(indexStateTrajList, len(probTrajList), 3):
            t_node = probTrajList[i]

            if not nodeIsInState(self.death_node, t_node):
                if nodeIsInState(self.division_node, t_node):
                    upPopRatio += 2*float(probTrajList[i+1])
                else:
                    upPopRatio += float(probTrajList[i+1])

        return upPopRatio

    def _initCond_Trajline(self, proba_traj_list):

        lineInitCond = "[%s" % self.node_list[0]
        for node in self.node_list[1:]:
            lineInitCond += ",%s" % node
        lineInitCond += "].istate ="

        for i in range(0, len(proba_traj_list), 3):
            t_proba_traj = proba_traj_list[i]

            lineInitCond += proba_traj_list[i+1] + " ["
            if nodeIsInState(self.node_list[0], t_proba_traj):
                lineInitCond += "1"
            else:
                lineInitCond += "0"

            for t_node in self.node_list[1:]:
                lineInitCond += ","
                if nodeIsInState(t_node, t_proba_traj):
                    lineInitCond += "1"
                else:
                    lineInitCond += "0"

            lineInitCond += "] , "

        lineInitCond = lineInitCond[:-2]
        lineInitCond += ";"

        return lineInitCond

def nodeIsInState(node, state):
    return (
        state == node 
        or state.startswith(node+" ") 
        or state.endswith(" "+node) 
        or (" %s " % node) in state
    )


def varDef_Upp(update_line, prob_traj_list):

	res_match = re.findall("p\[[^\[]*\]", update_line)
	if len(res_match) == 0:
		print("Syntax error in the parameter update definition : %s" % update_line, file=sys.stderr)
		exit()
	
	for match in res_match:

		lhs, rhs = match.split("=")
		lhs = lhs.replace("p[", "").replace("]", "").replace("(", "").replace(")", "")
		rhs = rhs.replace("[", "").replace("]", "").replace("(", "").replace(")", "")

		node_list = lhs.split(",")
		boolVal_list = rhs.split(",") 
		
		if len(node_list) != len(boolVal_list):
			print("Wrong probability definitions for \"%s\"" % match)
			exit()

		upNodeList = []
		downNodeList = []

		for i, node in enumerate(node_list):
			if float(boolVal_list[i]) == 0.0:
				downNodeList.append(node)
			else:
				upNodeList.append(node)

		probValue = 0.0
		for i in range(0, len(prob_traj_list), 3):
			upNodeProbTraj = prob_traj_list[i].split(" -- ")
			interlength = 0

			for upNodePt in upNodeProbTraj:
				for upNode in upNodeList:
					if upNodePt == upNode:
						interlength += 1

			if interlength == len(upNodeList):
				interlength = 0
				for upNodePt in upNodeProbTraj:
					for downNode in downNodeList:
						if upNodePt == downNode:
							interlength = 1
							break
					
					if interlength == 1:
						break
				if interlength == 0:
					probValue += float(prob_traj_list[i+1])

		update_line = update_line.replace(match, str(probValue), 1)
	update_line += ";"
	return update_line
	
def _get_next_condition_from_trajectory(self, next_model, step=16, pickline=5):
    names = [ n for n in self.model.network.names ]
    name2idx = {}
    for i in range(len(names)): name2idx[ names[i] ] = i
    
    
    trajfile = self.cfgfile.replace(".cfg","_Step_%s_probtraj.csv" % step)
    with open(trajfile) as f:
        for i in range(pickline): f.readline()
        data = f.readline().strip('\n').split('\t')
        states = [ _str2state(s,name2idx) for s in data[5::3] ]
        probs = [float(v) for v in data[6::3]]
    probDict = {}
    for state,prob in zip(states, probs):
        probDict[tuple(state)] = prob
    
    next_model.network.set_istate(names, probDict)


def _str2state(s, name2idx):
    state = [ 0 for n in name2idx]
    if '<nil>' != s:
        for n in s.split(' -- '):
            state[name2idx[n]] = 1
    return state


