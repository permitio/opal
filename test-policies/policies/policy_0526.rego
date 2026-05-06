package audit.authentication.resource.check.policy_0526

# Auto-generated policy 526 (Rego v1 syntax)
# Package: audit.authentication.resource.check

# Metadata
metadata := {
    "policy_id": "0526",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0526_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0526_allowed if {
    data.policies.audit.enabled
}
default policy_0526_allowed = false
policy_0526_allowed if {
    input.user.active
    input.resource.public
}
