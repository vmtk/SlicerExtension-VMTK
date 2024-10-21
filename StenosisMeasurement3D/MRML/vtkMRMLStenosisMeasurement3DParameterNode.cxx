#include "vtkMRMLStenosisMeasurement3DParameterNode.h"

// VTK includes
#include <vtkNew.h>
#include <vtkObjectFactory.h>

// MRML includes
#include <vtkMRMLMarkupsShapeNode.h>
#include <vtkMRMLMarkupsFiducialNode.h>
#include <vtkMRMLSegmentationNode.h>
#include <vtkMRMLModelNode.h>
#include <vtkMRMLTableNode.h>

static const char* InputShapeNodeReferenceRole = "inputShape";
static const char* InputFiducialNodeReferenceRole = "inputFiducial";
static const char* InputSegmentationNodeReferenceRole = "inputSegmentation";
static const char* OutputWallModelNodeReferenceRole = "outputWallModel";
static const char* OutputLumenModelNodeReferenceRole = "outputLumenModel";
static const char* OutputTableNodeReferenceRole = "outputTable";

//----------------------------------------------------------------------------
vtkMRMLNodeNewMacro(vtkMRMLStenosisMeasurement3DParameterNode);

//----------------------------------------------------------------------------
vtkMRMLStenosisMeasurement3DParameterNode::vtkMRMLStenosisMeasurement3DParameterNode()
{
  this->HideFromEditors = 1;
  this->AddToSceneOn();

  this->AddNodeReferenceRole(InputShapeNodeReferenceRole);
  this->AddNodeReferenceRole(InputFiducialNodeReferenceRole);
  this->AddNodeReferenceRole(InputSegmentationNodeReferenceRole);
  this->AddNodeReferenceRole(OutputWallModelNodeReferenceRole);
  this->AddNodeReferenceRole(OutputLumenModelNodeReferenceRole);
  this->AddNodeReferenceRole(OutputTableNodeReferenceRole);
}

//----------------------------------------------------------------------------
vtkMRMLStenosisMeasurement3DParameterNode::~vtkMRMLStenosisMeasurement3DParameterNode() = default;

//----------------------------------------------------------------------------
void vtkMRMLStenosisMeasurement3DParameterNode::SetScene(vtkMRMLScene* scene)
{
  Superclass::SetScene(scene);
  if (scene && !this->GetName())
  {
    const std::string name = scene->GenerateUniqueName(this->GetNodeTagName());
    this->SetName(name.c_str());
  }
}


//----------------------------------------------------------------------------
void vtkMRMLStenosisMeasurement3DParameterNode::PrintSelf(ostream& os, vtkIndent indent)
{
  Superclass::PrintSelf(os,indent);
  vtkMRMLPrintBeginMacro(os, indent);
  vtkMRMLPrintStdStringMacro(InputSegmentID);
  vtkMRMLPrintEndMacro();
}

//----------------------------------------------------------------------------
void vtkMRMLStenosisMeasurement3DParameterNode::ReadXMLAttributes(const char** atts)
{
  // Read all MRML node attributes from two arrays of names and values
  int disabledModify = this->StartModify();
  
  Superclass::ReadXMLAttributes(atts);
  
  vtkMRMLReadXMLBeginMacro(atts);
  vtkMRMLReadXMLStringMacro(segmentID, InputSegmentID);
  vtkMRMLReadXMLEndMacro();
  
  this->EndModify(disabledModify);
}

//----------------------------------------------------------------------------
void vtkMRMLStenosisMeasurement3DParameterNode::WriteXML(ostream& of, int nIndent)
{
  Superclass::WriteXML(of, nIndent);
  vtkMRMLWriteXMLBeginMacro(of);
  vtkMRMLWriteXMLStringMacro(segmentID, InputSegmentID);
  vtkMRMLWriteXMLEndMacro();
}

//----------------------------------------------------------------------------
void vtkMRMLStenosisMeasurement3DParameterNode::CopyContent(vtkMRMLNode* anode, bool deepCopy/*=true*/)
{
  MRMLNodeModifyBlocker blocker(this);
  Superclass::CopyContent(anode, deepCopy);
  
  vtkMRMLCopyBeginMacro(anode);
  vtkMRMLCopyStringMacro(InputSegmentID);
  vtkMRMLCopyEndMacro();
}

//----------------------------------------------------------------------------
void vtkMRMLStenosisMeasurement3DParameterNode::SetInputShapeNodeID(const char *nodeID)
{
  this->SetNodeReferenceID(InputShapeNodeReferenceRole, nodeID);
}

//----------------------------------------------------------------------------
const char * vtkMRMLStenosisMeasurement3DParameterNode::GetInputShapeNodeID()
{
  return this->GetNodeReferenceID(InputShapeNodeReferenceRole);
}

//----------------------------------------------------------------------------
vtkMRMLMarkupsShapeNode* vtkMRMLStenosisMeasurement3DParameterNode::GetInputShapeNode()
{
  return vtkMRMLMarkupsShapeNode::SafeDownCast(this->GetNodeReference(InputShapeNodeReferenceRole));
}

//----------------------------------------------------------------------------
void vtkMRMLStenosisMeasurement3DParameterNode::SetInputFiducialNodeID(const char *nodeID)
{
  this->SetNodeReferenceID(InputFiducialNodeReferenceRole, nodeID);
}

//----------------------------------------------------------------------------
const char * vtkMRMLStenosisMeasurement3DParameterNode::GetInputFiducialNodeID()
{
  return this->GetNodeReferenceID(InputFiducialNodeReferenceRole);
}

//----------------------------------------------------------------------------
vtkMRMLMarkupsFiducialNode* vtkMRMLStenosisMeasurement3DParameterNode::GetInputFiducialNode()
{
  return vtkMRMLMarkupsFiducialNode::SafeDownCast(this->GetNodeReference(InputFiducialNodeReferenceRole));
}

//----------------------------------------------------------------------------
void vtkMRMLStenosisMeasurement3DParameterNode::SetInputSegmentationNodeID(const char *nodeID)
{
  this->SetNodeReferenceID(InputSegmentationNodeReferenceRole, nodeID);
}

//----------------------------------------------------------------------------
const char * vtkMRMLStenosisMeasurement3DParameterNode::GetInputSegmentationNodeID()
{
  return this->GetNodeReferenceID(InputSegmentationNodeReferenceRole);
}

//----------------------------------------------------------------------------
vtkMRMLSegmentationNode* vtkMRMLStenosisMeasurement3DParameterNode::GetInputSegmentationNode()
{
  return vtkMRMLSegmentationNode::SafeDownCast(this->GetNodeReference(InputSegmentationNodeReferenceRole));
}

//----------------------------------------------------------------------------
void vtkMRMLStenosisMeasurement3DParameterNode::SetOutputWallModelNodeID(const char *nodeID)
{
  this->SetNodeReferenceID(OutputWallModelNodeReferenceRole, nodeID);
}

//----------------------------------------------------------------------------
const char * vtkMRMLStenosisMeasurement3DParameterNode::GetOutputWallModelNodeID()
{
  return this->GetNodeReferenceID(OutputWallModelNodeReferenceRole);
}

//----------------------------------------------------------------------------
vtkMRMLModelNode* vtkMRMLStenosisMeasurement3DParameterNode::GetOutputWallModelNode()
{
  return vtkMRMLModelNode::SafeDownCast(this->GetNodeReference(OutputWallModelNodeReferenceRole));
}

//----------------------------------------------------------------------------
void vtkMRMLStenosisMeasurement3DParameterNode::SetOutputLumenModelNodeID(const char *nodeID)
{
  this->SetNodeReferenceID(OutputLumenModelNodeReferenceRole, nodeID);
}

//----------------------------------------------------------------------------
const char * vtkMRMLStenosisMeasurement3DParameterNode::GetOutputLumenModelNodeID()
{
  return this->GetNodeReferenceID(OutputLumenModelNodeReferenceRole);
}

//----------------------------------------------------------------------------
vtkMRMLModelNode* vtkMRMLStenosisMeasurement3DParameterNode::GetOutputLumenModelNode()
{
  return vtkMRMLModelNode::SafeDownCast(this->GetNodeReference(OutputLumenModelNodeReferenceRole));
}

//----------------------------------------------------------------------------
void vtkMRMLStenosisMeasurement3DParameterNode::SetOutputTableNodeID(const char *nodeID)
{
  this->SetNodeReferenceID(OutputTableNodeReferenceRole, nodeID);
}

//----------------------------------------------------------------------------
const char * vtkMRMLStenosisMeasurement3DParameterNode::GetOutputTableNodeID()
{
  return this->GetNodeReferenceID(OutputTableNodeReferenceRole);
}

//----------------------------------------------------------------------------
vtkMRMLTableNode* vtkMRMLStenosisMeasurement3DParameterNode::GetOutputTableNode()
{
  return vtkMRMLTableNode::SafeDownCast(this->GetNodeReference(OutputTableNodeReferenceRole));
}
