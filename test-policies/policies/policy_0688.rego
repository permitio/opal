package governance.validation.resource.verify.core.policy_0688

# Auto-generated policy 688 (Rego v1 syntax)
# Package: governance.validation.resource.verify.core

# Metadata
metadata := {
    "policy_id": "0688",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0688_allowed = false
policy_0688_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
