#pragma once

#include "JsonObjectConverter.h"
#include "UObject/UnrealType.h"

namespace FigmaJson
{
// Figma uses its own "type" discriminator, not Unreal's UObject class metadata.
// Document, Children, Trigger and Actions are created by the parser explicitly.
// Do not let the generic converter instantiate them (UE 5.8 requires Instanced).
inline bool ImportObject(const TSharedRef<FJsonObject>& Json, UObject* Object, FText* OutFailReason = nullptr)
{
	const FJsonObjectConverter::CustomImportCallback ImportCallback =
		FJsonObjectConverter::CustomImportCallback::CreateLambda(
			[](const TSharedPtr<FJsonValue>& Value, FProperty* Property, void* OutValue)
			{
				if (CastField<FObjectPropertyBase>(Property))
				{
					return true;
				}
				const FArrayProperty* Array = CastField<FArrayProperty>(Property);
				return Array && CastField<FObjectPropertyBase>(Array->Inner);
			});
	return FJsonObjectConverter::JsonObjectToUStruct(Json, Object->GetClass(), Object,
		0, 0, false, OutFailReason, &ImportCallback);
}
}
