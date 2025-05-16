#ifndef __vtkmrmlstenosismeasurement3dlesionmodeldisplaynode_h_
#define __vtkmrmlstenosismeasurement3dlesionmodeldisplaynode_h_

#include "vtkMRML.h"
#include "vtkMRMLScene.h"
#include "vtkMRMLNode.h"
#include "vtkMRMLModelDisplayNode.h"
#include "vtkSlicerStenosisMeasurement3DModuleMRMLExport.h"

class vtkStringArray;

/*
 * The sole purpose of this class is to allow customising the display of the
 * lesion model from the application startup file. A default node of this type
 * with all display preferences must be added to the scene for any effect.
 */
class VTK_SLICER_STENOSISMEASUREMENT3D_MODULE_MRML_EXPORT vtkMRMLStenosisMeasurement3DLesionModelDisplayNode
: public vtkMRMLModelDisplayNode
{
public:
  static vtkMRMLStenosisMeasurement3DLesionModelDisplayNode *New();
  vtkTypeMacro(vtkMRMLStenosisMeasurement3DLesionModelDisplayNode, vtkMRMLModelDisplayNode);
  void PrintSelf(ostream& os, vtkIndent indent) override;
  
  vtkMRMLNode* CreateNodeInstance() override;
  
  /// Set node attributes from XML attributes
  void ReadXMLAttributes( const char** atts) override;
  
  /// Write this node's information to a MRML file in XML format.
  void WriteXML(ostream& of, int indent) override;
  
  vtkMRMLCopyContentMacro(vtkMRMLStenosisMeasurement3DParameterNode);
  const char* GetNodeTagName() override {return "LesionModel";}

  bool RegisterModel(const char * id);
  bool IsModelRegistered(const char * id);

protected:
  vtkMRMLStenosisMeasurement3DLesionModelDisplayNode();
  ~vtkMRMLStenosisMeasurement3DLesionModelDisplayNode() override;
  
  vtkMRMLStenosisMeasurement3DLesionModelDisplayNode(const vtkMRMLStenosisMeasurement3DLesionModelDisplayNode&);
  void operator=(const vtkMRMLStenosisMeasurement3DLesionModelDisplayNode&);

  vtkSmartPointer<vtkStringArray> RegisteredID;
};

#endif // __vtkmrmlstenosismeasurement3dlesionmodeldisplaynode_h_
