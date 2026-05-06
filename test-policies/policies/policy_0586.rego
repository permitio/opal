package audit.enforcement.context.check.logic.policy_0586

# Auto-generated policy 586 (Rego v1 syntax)
# Package: audit.enforcement.context.check.logic

# Metadata
metadata := {
    "policy_id": "0586",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0586_allowed = false
policy_0586_allowed if {
    data.policies.audit.enabled
}
policy_0586_allowed if {
    input.user.active
    input.resource.public
}
policy_0586_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
