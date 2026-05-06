package governance.validation.context.validate.logic.policy_0261

# Auto-generated policy 261 (Rego v1 syntax)
# Package: governance.validation.context.validate.logic

# Metadata
metadata := {
    "policy_id": "0261",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0261_allowed if {
    input.user.role == "admin"
}
policy_0261_allowed if {
    input.user.active
    input.resource.public
}
policy_0261_allowed if {
    data.policies.governance.enabled
}
policy_0261_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
