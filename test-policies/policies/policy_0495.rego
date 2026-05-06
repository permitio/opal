package audit.validation.resource.verify.logic.policy_0495

# Auto-generated policy 495
# Package: audit.validation.resource.verify.logic

# Metadata
metadata := {
    "policy_id": "0495",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0495_allowed = false
policy_0495_allowed if {
    data.policies.audit.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
