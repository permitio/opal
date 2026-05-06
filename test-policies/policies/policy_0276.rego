package compliance.enforcement.action.verify.logic.policy_0276

# Auto-generated policy 276 (Rego v1 syntax)
# Package: compliance.enforcement.action.verify.logic

# Metadata
metadata := {
    "policy_id": "0276",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0276_allowed if {
    input.user.active
    input.resource.public
}
policy_0276_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0276_allowed = false
policy_0276_allowed if {
    data.policies.compliance.enabled
}
