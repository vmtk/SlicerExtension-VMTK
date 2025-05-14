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
static const char* OutputLesionModelNodeReferenceRole = "outputLesionModel";
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
  this->AddNodeReferenceRole(OutputLesionModelNodeReferenceRole);
  this->AddNodeReferenceRole(OutputTableNodeReferenceRole);
}

//----------------------------------------------------------------------------
vtkMRMLStenosisMeasurement3DParameterNode::~vtkMRMLStenosisMeasurement3DParameterNode() = default;

//----------------------------------------------------------------------------
void vtkMRMLStenosisMeasurement3DParameterNode::PrintSelf(ostream& os, vtkIndent indent)
{
  Superclass::PrintSelf(os,indent);
  vtkMRMLPrintBeginMacro(os, indent);
  vtkMRMLPrintStdStringMacro(InputSegmentID);
  vtkMRMLPrintIntMacro(OutputTableRowId);
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
  vtkMRMLReadXMLIntMacro(tableRowId, OutputTableRowId)
  vtkMRMLReadXMLEndMacro();
  
  this->EndModify(disabledModify);
}

//----------------------------------------------------------------------------
void vtkMRMLStenosisMeasurement3DParameterNode::WriteXML(ostream& of, int nIndent)
{
  Superclass::WriteXML(of, nIndent);
  vtkMRMLWriteXMLBeginMacro(of);
  vtkMRMLWriteXMLStringMacro(segmentID, InputSegmentID);
  vtkMRMLWriteXMLIntMacro(tableRowId, OutputTableRowId);
  vtkMRMLWriteXMLEndMacro();
}

//----------------------------------------------------------------------------
void vtkMRMLStenosisMeasurement3DParameterNode::CopyContent(vtkMRMLNode* anode, bool deepCopy/*=true*/)
{
  MRMLNodeModifyBlocker blocker(this);
  Superclass::CopyContent(anode, deepCopy);
  
  vtkMRMLCopyBeginMacro(anode);
  vtkMRMLCopyStringMacro(InputSegmentID);
  vtkMRMLCopyIntMacro(OutputTableRowId);
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
void vtkMRMLStenosisMeasurement3DParameterNode::SetOutputLesionModelNodeID(const char *nodeID)
{
  this->SetNodeReferenceID(OutputLesionModelNodeReferenceRole, nodeID);
}

//----------------------------------------------------------------------------
const char * vtkMRMLStenosisMeasurement3DParameterNode::GetOutputLesionModelNodeID()
{
  return this->GetNodeReferenceID(OutputLesionModelNodeReferenceRole);
}

//----------------------------------------------------------------------------
vtkMRMLModelNode* vtkMRMLStenosisMeasurement3DParameterNode::GetOutputLesionModelNode()
{
  return vtkMRMLModelNode::SafeDownCast(this->GetNodeReference(OutputLesionModelNodeReferenceRole));
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
