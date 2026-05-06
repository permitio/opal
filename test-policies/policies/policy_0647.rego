package compliance.enforcement.resource.verify.policy_0647

# Auto-generated policy 647 (Rego v1 syntax)
# Package: compliance.enforcement.resource.verify

# Metadata
metadata := {
    "policy_id": "0647",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0647_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0647_allowed if {
    input.user.active
    input.resource.public
}
policy_0647_allowed if {
    data.policies.compliance.enabled
}
default policy_0647_allowed = false
