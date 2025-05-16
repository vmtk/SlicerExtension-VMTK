#include "vtkMRMLStenosisMeasurement3DLesionModelDisplayNode.h"

// VTK includes
#include <vtkNew.h>
#include <vtkObjectFactory.h>
#include <vtkStringArray.h>

//----------------------------------------------------------------------------
vtkMRMLNodeNewMacro(vtkMRMLStenosisMeasurement3DLesionModelDisplayNode);

//----------------------------------------------------------------------------
vtkMRMLStenosisMeasurement3DLesionModelDisplayNode::vtkMRMLStenosisMeasurement3DLesionModelDisplayNode()
{
  this->HideFromEditors = 1;
  this->AddToSceneOn();
  this->RegisteredID = vtkSmartPointer<vtkStringArray>::New();
}

//----------------------------------------------------------------------------
vtkMRMLStenosisMeasurement3DLesionModelDisplayNode::~vtkMRMLStenosisMeasurement3DLesionModelDisplayNode() = default;

//----------------------------------------------------------------------------
void vtkMRMLStenosisMeasurement3DLesionModelDisplayNode::PrintSelf(ostream& os, vtkIndent indent)
{
  Superclass::PrintSelf(os,indent);
  vtkMRMLPrintBeginMacro(os, indent);
  vtkMRMLPrintEndMacro();
}

//----------------------------------------------------------------------------
void vtkMRMLStenosisMeasurement3DLesionModelDisplayNode::ReadXMLAttributes(const char** atts)
{
  // Read all MRML node attributes from two arrays of names and values
  int disabledModify = this->StartModify();
  
  Superclass::ReadXMLAttributes(atts);
  
  vtkMRMLReadXMLBeginMacro(atts);
  vtkMRMLReadXMLEndMacro();
  
  this->EndModify(disabledModify);
}

//----------------------------------------------------------------------------
void vtkMRMLStenosisMeasurement3DLesionModelDisplayNode::WriteXML(ostream& of, int nIndent)
{
  Superclass::WriteXML(of, nIndent);
  vtkMRMLWriteXMLBeginMacro(of);
  vtkMRMLWriteXMLEndMacro();
}

//----------------------------------------------------------------------------
void vtkMRMLStenosisMeasurement3DLesionModelDisplayNode::CopyContent(vtkMRMLNode* anode, bool deepCopy/*=true*/)
{
  MRMLNodeModifyBlocker blocker(this);
  Superclass::CopyContent(anode, deepCopy);
  
  vtkMRMLCopyBeginMacro(anode);
  vtkMRMLCopyEndMacro();
}

//----------------------------------------------------------------------------
bool vtkMRMLStenosisMeasurement3DLesionModelDisplayNode::RegisterModel(const char* id)
{
  if (this->IsModelRegistered(id))
  {
    return false;
  }
  this->RegisteredID->InsertNextValue(id);
  return true;
}

//----------------------------------------------------------------------------
bool vtkMRMLStenosisMeasurement3DLesionModelDisplayNode::IsModelRegistered(const char* id)
{
  for (vtkIdType i = 0; i < this->RegisteredID->GetNumberOfValues(); i++)
  {
    if (this->RegisteredID->GetValue(i) == vtkStdString(id))
    {
      return true;
    }
  }
  return false;
}
