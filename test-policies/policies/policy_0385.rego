package governance.validation.resource.check.policy_0385

# Auto-generated policy 385 (Rego v1 syntax)
# Package: governance.validation.resource.check

# Metadata
metadata := {
    "policy_id": "0385",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0385_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0385_allowed if {
    input.user.active
    input.resource.public
}
policy_0385_allowed if {
    data.policies.governance.enabled
}
policy_0385_allowed if {
    input.user.role == "admin"
}
